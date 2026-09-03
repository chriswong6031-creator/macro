"""MOR-1 route-semantic evidence contract (companion to the generic 8-cell gate).

The fleet checker ``scripts/check_ui_visual_evidence.py`` proves mechanical REST
coverage (desktop/mobile × en/zh × dark/light) per ``manifest.pages[]`` row. It
does not prove route semantics. This module owns the frozen 4 route-case × 8
REST = 32-cell acceptance matrix for Market Reference and rejects the historical
false-complete pattern (one default-route page + three ``excluded`` rows).

No second screenshot plane: it reads the existing ``mastermind.p0_evidence.v2``
manifest the capture harness already writes, plus optional per-state
``route_state`` fields the harness emits.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

SCHEMA = "mastermind.p0_evidence.v2"

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


def _rest_key(state: Mapping[str, Any]) -> tuple[str, str, str] | None:
    viewport = state.get("viewport")
    locale = state.get("locale")
    theme = state.get("theme")
    if not isinstance(viewport, str) or not isinstance(locale, str) or not isinstance(theme, str):
        return None
    if state.get("force_state") not in (None,):
        return None
    return (viewport, locale, theme)


def validate_manifest_route_matrix(manifest: Mapping[str, Any]) -> list[str]:
    """Return human-readable defects; empty list means the 32-cell contract holds."""

    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return ["manifest top level must be an object"]
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, got {manifest.get('schema')!r}")

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        return errors + ["manifest.pages must be a non-empty list"]

    by_page_id = {p.get("page_id"): p for p in pages if isinstance(p, Mapping)}
    by_route = {p.get("route"): p for p in pages if isinstance(p, Mapping)}

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
            if not state.get("captured"):
                errors.append(f"page {page_id!r} cell {key}: not captured")
                continue
            present.add(key)
            sha = state.get("sha256")
            if isinstance(sha, str) and sha:
                digests.setdefault(sha, []).append(key)
            route_errs = _validate_route_state(case, state)
            errors.extend(f"page {page_id!r} cell {key}: {err}" for err in route_errs)
        missing = sorted(REQUIRED_REST_KEYS - present)
        if missing:
            errors.append(f"page {page_id!r}: missing REST cells {missing}")
        # Distinct route cases must not share a screenshot digest unless every
        # sharing cell carries matching route_state proof (byte-identical OK only
        # within the same page_id).
        for sha, cells in digests.items():
            if len(cells) > 1:
                # Same page REST matrix may legally share nothing usually; warn
                # only when route_state disagrees — handled per-cell above.
                pass

    # Cross-page: one PNG digest used for two different required routes is a mutant.
    digest_owners: dict[str, set[str]] = {}
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        route = page.get("route")
        if route not in REQUIRED_ROUTE_SET:
            continue
        for state in page.get("states") or []:
            if not isinstance(state, Mapping) or not state.get("captured"):
                continue
            sha = state.get("sha256")
            if isinstance(sha, str) and sha:
                digest_owners.setdefault(sha, set()).add(str(route))
    for sha, routes in digest_owners.items():
        if len(routes) > 1:
            errors.append(
                f"screenshot digest {sha[:16]}… reused across distinct routes {sorted(routes)} "
                "without per-route isolation"
            )

    extra_required_looking = [
        p.get("page_id")
        for p in pages
        if isinstance(p, Mapping)
        and p.get("route") in REQUIRED_ROUTE_SET
        and p.get("page_id") not in REQUIRED_PAGE_IDS
        and p.get("page_id") not in {c["page_id"] for c in ROUTE_CASES}
    ]
    # Allow legacy page_id == route string only when route matches and we already
    # accepted via by_route; no extra error.

    return errors


def _validate_route_state(case: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    expect = case["expect"]
    rs = state.get("route_state")
    if not isinstance(rs, Mapping):
        return ["missing route_state (capture must record final URL / DOM route probe)"]
    errors: list[str] = []
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
    if bool(rs.get("miss_visible")) != bool(expect.get("miss_visible")):
        errors.append(
            f"miss_visible {rs.get('miss_visible')!r} != expected {expect.get('miss_visible')!r}"
        )
    want_sel = expect.get("selected_id")
    got_sel = rs.get("selected_id")
    if want_sel is None:
        if got_sel not in (None, ""):
            # Unknown-anchor and default must not claim a selected entry.
            if case["case_id"] in {"default", "unknown_anchor", "query_curve"}:
                errors.append(f"selected_id {got_sel!r} expected null")
    elif got_sel != want_sel:
        errors.append(f"selected_id {got_sel!r} != expected {want_sel!r}")
    min_results = expect.get("min_visible_results")
    if isinstance(min_results, int):
        count = rs.get("visible_result_count")
        if not isinstance(count, int) or count < min_results:
            errors.append(
                f"visible_result_count {count!r} < required minimum {min_results}"
            )
    requested = rs.get("requested_url")
    final = rs.get("final_url")
    if not isinstance(requested, str) or not requested:
        errors.append("requested_url missing")
    if not isinstance(final, str) or not final:
        errors.append("final_url missing")
    # Route path/query/hash must appear in the final browser URL.
    route = str(case["route"])
    if isinstance(final, str):
        if route.startswith("http"):
            pass
        else:
            # Compare by suffix path+search+hash
            if "?" in route or "#" in route:
                marker = route.split("/")[-1]
            else:
                marker = route
            if marker not in final and not final.endswith(route):
                # Allow absolute URL ending with the route marker.
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
