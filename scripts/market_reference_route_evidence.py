"""MOR-1 route-semantic evidence contract (companion to the generic 8-cell gate).

The fleet checker ``scripts/check_ui_visual_evidence.py`` proves mechanical REST
coverage (desktop/mobile × en/zh × dark/light) per ``manifest.pages[]`` row. It
does not prove route semantics. This module owns the frozen 4 route-case × 8
REST = 32-cell acceptance matrix for Market Reference and rejects the historical
false-complete pattern (one default-route page + three ``excluded`` rows).

No second screenshot plane: it reads the existing ``mastermind.p0_evidence.v2``
manifest the capture harness already writes, plus per-state ``route_state``
fields and optional ``candidate_binding``.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "mastermind.p0_evidence.v2"
MIN_TOOL_VERSION = (1, 3, 0)

# Frozen acceptance matrix — do not rename/drop without DECISION_REQUEST.
ROUTE_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "default",
        "page_id": "reference_default",
        "route": "reference.html",
        "expect": {
            "hash": "",
            "query_q": None,
            "miss_visible": False,
            "selected_id": None,
            "require_focus": False,
            "require_journeys": True,
        },
    },
    {
        "case_id": "valid_anchor",
        "page_id": "reference_vix",
        "route": "reference.html#vix",
        "expect": {
            "hash": "#vix",
            "query_q": None,
            "miss_visible": False,
            "selected_id": "vix",
            "require_focus": True,
            "require_journeys": True,
        },
    },
    {
        "case_id": "unknown_anchor",
        "page_id": "reference_unknown_anchor",
        "route": "reference.html#not-a-real-entry",
        "expect": {
            "hash": "#not-a-real-entry",
            "query_q": None,
            "miss_visible": True,
            "selected_id": None,
            "require_focus": False,
            "require_journeys": True,
        },
    },
    {
        "case_id": "query_curve",
        "page_id": "reference_query_curve",
        "route": "reference.html?q=curve",
        "expect": {
            "hash": "",
            "query_q": "curve",
            "miss_visible": False,
            "selected_id": None,
            "min_visible_results": 1,
            "require_focus": False,
            "require_journeys": True,
            "require_count_label": True,
            "require_membership": True,
        },
    },
)

REQUIRED_REST_KEYS = frozenset(
    {
        ("desktop", "en", "dark"),
        ("desktop", "en", "light"),
        ("desktop", "zh", "dark"),
        ("desktop", "zh", "light"),
        ("mobile", "en", "dark"),
        ("mobile", "en", "light"),
        ("mobile", "zh", "dark"),
        ("mobile", "zh", "light"),
    }
)

REQUIRED_ROUTE_SET = frozenset(case["route"] for case in ROUTE_CASES)
REQUIRED_PAGE_IDS = frozenset(case["page_id"] for case in ROUTE_CASES)

REQUIRED_ROUTE_STATE_KEYS = frozenset(
    {
        "requested_url",
        "final_url",
        "hash",
        "query_q",
        "rf_q_value",
        "miss_visible",
        "selected_id",
        "visible_result_count",
        "visible_entry_ids",
        "count_label_visible",
        "count_label_text",
        "focused_element_id",
        "focused_visible",
        "target_below_fixed_ui",
    }
)

REQUIRED_BINDING_KEYS = frozenset(
    {
        "source_commit",
        "source_tree",
        "site_reference_sha256",
        "serve_root",
        "capture_tool_version",
        "capture_tool_module_sha256",
    }
)

REQUIRED_JOURNEY_KEYS = frozenset(
    {"change", "clear", "reload", "back_forward", "share"}
)


def _parse_tool_version(raw: Any) -> tuple[int, ...] | None:
    if not isinstance(raw, str) or not raw:
        return None
    parts: list[int] = []
    for piece in raw.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
    return tuple(parts) if parts else None


def _rest_key(state: Mapping[str, Any]) -> tuple[str, str, str] | None:
    viewport = state.get("viewport")
    locale = state.get("locale")
    theme = state.get("theme")
    if not isinstance(viewport, str) or not isinstance(locale, str) or not isinstance(theme, str):
        return None
    if state.get("force_state") not in (None,):
        return None
    return (viewport, locale, theme)


def _png_dimensions(png: bytes) -> tuple[int, int] | None:
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", png[16:24])
    return int(width), int(height)


def _journey_ok(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if "ok" in payload:
        return bool(payload.get("ok"))
    return False


def validate_manifest_route_matrix(
    manifest: Mapping[str, Any],
    *,
    evidence_dir: Path | None = None,
) -> list[str]:
    """Return human-readable defects; empty list means the 32-cell contract holds."""

    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return ["manifest top level must be an object"]
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, got {manifest.get('schema')!r}")

    tool = manifest.get("tool") if isinstance(manifest.get("tool"), Mapping) else {}
    version = _parse_tool_version(tool.get("version") if isinstance(tool, Mapping) else None)
    if version is None or version < MIN_TOOL_VERSION:
        errors.append(
            f"capture tool version must be >={' .'.join(str(x) for x in MIN_TOOL_VERSION)}; "
            f"got {tool.get('version')!r}"
        )

    binding = manifest.get("candidate_binding")
    if not isinstance(binding, Mapping):
        errors.append("missing candidate_binding (source/tree/site/serve/capture identity)")
    else:
        for key in sorted(REQUIRED_BINDING_KEYS):
            val = binding.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"candidate_binding.{key} missing or empty")
        # Binding must not masquerade as nearest-git-only identity.
        target = manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
        nearest = target.get("resolved_sha_or_none") if isinstance(target, Mapping) else None
        source_commit = binding.get("source_commit") if isinstance(binding, Mapping) else None
        if (
            isinstance(source_commit, str)
            and isinstance(nearest, str)
            and source_commit
            and nearest
            and source_commit == nearest
            and "not verified" in str(target.get("resolved_sha_source") or "")
            and not binding.get("source_commit_verified")
        ):
            # Same SHA is fine when explicitly verified; unmarked equality with
            # an unverified nearest-git claim is not sufficient alone.
            if not binding.get("worktree_head_matches_source"):
                errors.append(
                    "candidate_binding.source_commit is not marked verified relative "
                    "to the capture worktree/serve root"
                )

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        return errors + ["manifest.pages must be a non-empty list"]

    # Duplicate page_id / route detection (do not silently collapse).
    page_ids: list[Any] = []
    routes: list[Any] = []
    for page in pages:
        if not isinstance(page, Mapping):
            errors.append("manifest.pages contains a non-object entry")
            continue
        page_ids.append(page.get("page_id"))
        routes.append(page.get("route"))
    for pid in {p for p in page_ids if page_ids.count(p) > 1}:
        errors.append(f"duplicate page_id {pid!r}")
    for route in {r for r in routes if routes.count(r) > 1}:
        errors.append(f"duplicate route row {route!r}")

    by_page_id = {
        p.get("page_id"): p for p in pages if isinstance(p, Mapping) and p.get("page_id") is not None
    }
    by_route = {
        p.get("route"): p for p in pages if isinstance(p, Mapping) and p.get("route") is not None
    }

    excluded = manifest.get("excluded") or []
    if isinstance(excluded, list):
        for item in excluded:
            if not isinstance(item, Mapping):
                continue
            route = item.get("route")
            if route in REQUIRED_ROUTE_SET:
                errors.append(
                    f"required route {route!r} is listed under excluded — "
                    "the historical eight-cell overclaim pattern"
                )

    logical_keys: list[tuple[Any, ...]] = []
    digest_owners: dict[str, set[str]] = {}
    manifest_files: set[str] = set()

    for case in ROUTE_CASES:
        page_id = case["page_id"]
        route = case["route"]
        page = by_page_id.get(page_id) or by_route.get(route)
        if page is None:
            errors.append(f"missing required route case {case['case_id']} ({route})")
            continue
        if page.get("route") != route:
            errors.append(
                f"page {page_id!r}: route {page.get('route')!r} != required {route!r}"
            )
        if page.get("page_id") not in REQUIRED_PAGE_IDS:
            errors.append(
                f"page for route {route!r} has unexpected page_id {page.get('page_id')!r}"
            )

        # Route-scoped console / failed responses must be empty for these static pages.
        for key in ("console_errors", "failed_responses"):
            bag = page.get(key) or []
            if isinstance(bag, list) and bag:
                errors.append(f"page {page_id!r}: unexpected {key}: {bag!r}")

        journeys = page.get("route_journeys")
        if case["expect"].get("require_journeys"):
            if not isinstance(journeys, Mapping):
                errors.append(f"page {page_id!r}: missing route_journeys")
            else:
                missing_j = sorted(REQUIRED_JOURNEY_KEYS - set(journeys))
                if missing_j:
                    errors.append(f"page {page_id!r}: route_journeys missing keys {missing_j}")
                for jkey in REQUIRED_JOURNEY_KEYS:
                    if jkey in journeys and not _journey_ok(journeys.get(jkey)):
                        errors.append(f"page {page_id!r}: journey {jkey} not ok: {journeys.get(jkey)!r}")

        states = page.get("states")
        if not isinstance(states, list):
            errors.append(f"page {page_id!r}: states must be a list")
            continue
        present: set[tuple[str, str, str]] = set()
        digests: dict[str, list[tuple[str, str, str]]] = {}
        for state in states:
            if not isinstance(state, Mapping):
                errors.append(f"page {page_id!r}: non-object state entry")
                continue
            key = _rest_key(state)
            if key is None:
                continue
            logical_keys.append((page_id, key[0], key[1], key[2]))
            if not state.get("captured"):
                errors.append(f"page {page_id!r} cell {key}: not captured")
                continue
            present.add(key)
            sha = state.get("sha256")
            if isinstance(sha, str) and sha:
                digests.setdefault(sha, []).append(key)
                digest_owners.setdefault(sha, set()).add(str(route))
            file_name = state.get("file")
            if isinstance(file_name, str) and file_name:
                manifest_files.add(Path(file_name).name)
            route_errs = _validate_route_state(case, state)
            errors.extend(f"page {page_id!r} cell {key}: {err}" for err in route_errs)
            # Unknown top-level state keys beyond the known capture shape are soft-
            # reported only when they collide with required semantics.
            if "unknown_state" in state and state.get("unknown_state"):
                errors.append(f"page {page_id!r} cell {key}: unknown_state flagged")
        missing = sorted(REQUIRED_REST_KEYS - present)
        if missing:
            errors.append(f"page {page_id!r}: missing REST cells {missing}")

    # Duplicate logical cells across the matrix.
    for logical in {k for k in logical_keys if logical_keys.count(k) > 1}:
        errors.append(f"duplicate logical cell {logical!r}")

    for sha, routes_hit in digest_owners.items():
        if len(routes_hit) > 1:
            errors.append(
                f"screenshot digest {sha[:16]}… reused across distinct routes {sorted(routes_hit)} "
                "without per-route isolation"
            )

    # PNG existence / hash / bytes / dimensions + unexpected extras.
    if evidence_dir is not None:
        ev = Path(evidence_dir)
        if not ev.is_dir():
            errors.append(f"evidence_dir not a directory: {ev}")
        else:
            disk_pngs = {p.name for p in ev.glob("*.png")}
            extras = sorted(disk_pngs - manifest_files)
            missing_files = sorted(manifest_files - disk_pngs)
            if extras:
                errors.append(f"unexpected PNG extras on disk: {extras}")
            if missing_files:
                errors.append(f"manifest PNG files missing on disk: {missing_files}")
            for page in pages:
                if not isinstance(page, Mapping):
                    continue
                for state in page.get("states") or []:
                    if not isinstance(state, Mapping) or not state.get("captured"):
                        continue
                    file_name = state.get("file")
                    if not isinstance(file_name, str) or not file_name:
                        errors.append("captured state missing file name")
                        continue
                    path = ev / Path(file_name).name
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != state.get("sha256"):
                        errors.append(
                            f"PNG hash mismatch for {path.name}: disk {digest[:16]}… "
                            f"!= manifest {str(state.get('sha256'))[:16]}…"
                        )
                    if len(data) != state.get("bytes"):
                        errors.append(
                            f"PNG bytes mismatch for {path.name}: disk {len(data)} "
                            f"!= manifest {state.get('bytes')!r}"
                        )
                    dims = _png_dimensions(data)
                    if dims is None:
                        errors.append(f"PNG not readable for {path.name}")
                    else:
                        w, h = dims
                        if w != state.get("width") or h != state.get("height"):
                            errors.append(
                                f"PNG dimensions mismatch for {path.name}: disk {(w, h)} "
                                f"!= manifest {(state.get('width'), state.get('height'))}"
                            )

    # Unexpected required-looking extras.
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        pid = page.get("page_id")
        route = page.get("route")
        if route in REQUIRED_ROUTE_SET and pid not in REQUIRED_PAGE_IDS:
            errors.append(f"unexpected extra required-route page_id {pid!r} for {route!r}")
        if isinstance(pid, str) and pid.startswith("reference_") and pid not in REQUIRED_PAGE_IDS:
            if route not in REQUIRED_ROUTE_SET:
                errors.append(f"unexpected extra page {pid!r} route {route!r}")

    return errors


def _validate_route_state(case: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    expect = case["expect"]
    rs = state.get("route_state")
    if not isinstance(rs, Mapping):
        return ["missing route_state (capture must record final URL / DOM route probe)"]
    errors: list[str] = []
    missing_keys = sorted(REQUIRED_ROUTE_STATE_KEYS - set(rs))
    if missing_keys:
        errors.append(f"route_state missing keys {missing_keys}")

    want_hash = expect.get("hash", "")
    got_hash = rs.get("hash")
    if got_hash != want_hash:
        errors.append(f"hash {got_hash!r} != expected {want_hash!r}")
    want_q = expect.get("query_q")
    got_q = rs.get("query_q")
    if want_q is None:
        if got_q not in (None, ""):
            errors.append(f"query_q {got_q!r} expected absent")
    elif got_q != want_q:
        errors.append(f"query_q {got_q!r} != expected {want_q!r}")
    if want_q is not None and rs.get("rf_q_value") not in (want_q, str(want_q)):
        errors.append(f"rf_q_value {rs.get('rf_q_value')!r} != expected {want_q!r}")
    if bool(rs.get("miss_visible")) != bool(expect.get("miss_visible")):
        errors.append(
            f"miss_visible {rs.get('miss_visible')!r} != expected {expect.get('miss_visible')!r}"
        )
    want_sel = expect.get("selected_id")
    got_sel = rs.get("selected_id")
    if want_sel is None:
        if got_sel not in (None, ""):
            if case["case_id"] in {"default", "unknown_anchor", "query_curve"}:
                errors.append(f"selected_id {got_sel!r} expected null")
    elif got_sel != want_sel:
        errors.append(f"selected_id {got_sel!r} != expected {want_sel!r}")

    min_results = expect.get("min_visible_results")
    count = rs.get("visible_result_count")
    if isinstance(min_results, int):
        if not isinstance(count, int) or count < min_results:
            errors.append(
                f"visible_result_count {count!r} < required minimum {min_results}"
            )

    if expect.get("require_membership"):
        ids = rs.get("visible_entry_ids")
        if not isinstance(ids, list) or not ids:
            errors.append("visible_entry_ids missing or empty")
        elif isinstance(count, int) and len(ids) != count:
            errors.append(
                f"visible_entry_ids length {len(ids)} != visible_result_count {count}"
            )

    if expect.get("require_count_label"):
        if not rs.get("count_label_visible"):
            errors.append("count_label_visible is false")
        label = rs.get("count_label_text")
        values = rs.get("count_label_values")
        if not isinstance(label, str) or not label.strip():
            errors.append("count_label_text missing")
        if isinstance(count, int):
            count_str = str(count)
            label_ok = isinstance(label, str) and count_str in label
            values_ok = isinstance(values, list) and any(str(v) == count_str for v in values)
            if not (label_ok or values_ok):
                errors.append(
                    f"count label does not reflect visible_result_count {count}: "
                    f"text={label!r} values={values!r}"
                )

    if expect.get("require_focus"):
        if got_sel != want_sel:
            errors.append(f"selected_id {got_sel!r} != expected {want_sel!r} for focus case")
        if not rs.get("focused_visible"):
            errors.append("focused_visible is false for valid-anchor case")
        if rs.get("target_below_fixed_ui") is not True:
            errors.append(
                f"target_below_fixed_ui {rs.get('target_below_fixed_ui')!r} is not true"
            )
        focused = rs.get("focused_element_id")
        # `.rf-sum` may have no id; accept null focus id only when selected_id matches
        # and focus is visibly on the opened entry (focused_visible already required).
        if focused not in (None, "", want_sel) and not (
            isinstance(focused, str) and want_sel and want_sel in focused
        ):
            errors.append(f"focused_element_id {focused!r} does not name {want_sel!r}")

    requested = rs.get("requested_url")
    final = rs.get("final_url")
    if not isinstance(requested, str) or not requested:
        errors.append("requested_url missing")
    if not isinstance(final, str) or not final:
        errors.append("final_url missing")
    route = str(case["route"])
    if isinstance(final, str) and not route.startswith("http"):
        marker = route.split("/")[-1]
        if marker not in final and not final.endswith(route):
            if not any(final.endswith(part) or part in final for part in (route, marker)):
                errors.append(f"final_url {final!r} does not reflect route {route!r}")
    return errors


def assert_historical_overclaim_is_red(manifest: Mapping[str, Any]) -> None:
    """Discriminating RED: the committed eight-default + excluded trio must fail."""

    errors = validate_manifest_route_matrix(manifest)
    if not errors:
        raise AssertionError(
            "historical overclaim manifest unexpectedly validated; "
            "route matrix checker lost its discriminating power"
        )
    joined = "\n".join(errors)
    if "excluded" not in joined and "missing required route case" not in joined:
        raise AssertionError(
            "expected excluded-route / missing-case defects, got:\n" + joined
        )


def mor1_capture_rows() -> list[dict[str, Any]]:
    """Explicit capture rows for the four frozen route cases (no registry lookup)."""

    rows: list[dict[str, Any]] = []
    for case in ROUTE_CASES:
        rows.append(
            {
                "page_id": case["page_id"],
                "route": case["route"],
                "capture_route": case["route"],
                "repo": "",
                "priority": "",
                "route_kind": "mor1_route_case",
                "is_family": False,
                "exemplar": None,
                "themes": None,
                "locales": None,
                "mor1_case_id": case["case_id"],
            }
        )
    return rows
