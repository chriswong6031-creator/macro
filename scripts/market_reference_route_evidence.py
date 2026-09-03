"""MOR-1 route-semantic evidence contract (companion to the generic 8-cell gate).

The fleet checker ``scripts/check_ui_visual_evidence.py`` proves mechanical REST
coverage (desktop/mobile × en/zh × dark/light) per ``manifest.pages[]`` row. It
does not prove route semantics. This module owns the frozen 4 route-case × 8
REST = 32-cell acceptance matrix for Market Reference and rejects the historical
false-complete pattern (one default-route page + three ``excluded`` rows).

No second screenshot plane: it reads the existing ``mastermind.p0_evidence.v2``
manifest the capture harness already writes, plus per-state ``route_state``
fields and ``candidate_binding``.
"""

from __future__ import annotations

import hashlib
import re
import struct
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

SCHEMA = "mastermind.p0_evidence.v2"
MIN_TOOL_VERSION = (1, 4, 0)
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Mirrors templates/reference.html.j2 ``normalize()``.
_JS_STRIP = re.compile(r"[\s　-〿＀-￯!-\/:-@\[-`{-~]")

REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_VIEWPORTS = frozenset({"desktop", "mobile"})
ALLOWED_LOCALES = frozenset({"en", "zh"})
ALLOWED_THEMES = frozenset({"dark", "light"})

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
            "require_full_library": True,
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
            "require_full_library": True,
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
            "require_full_library": True,
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

REQUIRED_RENDER_INPUTS = ("templates/reference.html.j2", "config/market_reference.yml")
REQUIRED_JOURNEY_KEYS = frozenset(
    {"change", "clear", "reload", "back", "forward", "share"}
)
REQUIRED_SHARED_ASSETS = (
    "site/theme.css",
    "site/navigation-refresh.css",
    "site/theme.js",
    "site/logo_config.js",
    "site/stock-logos.js",
    "site/live_config.js",
    "site/live.js",
)


def js_normalize_query(raw: str) -> str:
    """Byte-equivalent of the page ``normalize()`` helper for ``?q=`` matching."""

    s = unicodedata.normalize("NFKC", raw or "")
    s = s.lower()
    return _JS_STRIP.sub("", s)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout or "").strip()


def expected_query_entry_ids(query: str | None, *, repo_root: Path) -> list[str]:
    """Exact visible-id set under the page's current ``data-search`` predicate."""

    from scripts.build_market_reference import load_registry, search_key

    registry_path = repo_root / "config" / "market_reference.yml"
    raw = load_registry(registry_path)
    entries = list(raw.get("entries") or [])
    qn = js_normalize_query(query or "")
    if not qn:
        return [str(e.get("id")) for e in entries if e.get("id")]
    hits: list[str] = []
    for entry in entries:
        eid = entry.get("id")
        if not eid:
            continue
        if qn in search_key(entry):
            hits.append(str(eid))
    return hits


def _href_query(href: Any) -> str | None:
    if not isinstance(href, str) or not href:
        return None
    try:
        values = parse_qs(urlparse(href).query).get("q")
    except Exception:
        return None
    if not values:
        return None
    return values[0]


def _href_hash(href: Any) -> str:
    if not isinstance(href, str) or not href:
        return ""
    try:
        fragment = urlparse(href).fragment or ""
    except Exception:
        return ""
    return f"#{fragment}" if fragment else ""


def _route_in_href(href: Any, route: str) -> bool:
    if not isinstance(href, str) or not href:
        return False
    marker = route.split("/")[-1]
    return marker in href or href.endswith(route)


def _validate_journeys(
    case: Mapping[str, Any],
    journeys: Mapping[str, Any],
    *,
    expected_ids_for_query,
    full_library_ids: Sequence[str],
) -> list[str]:
    errors: list[str] = []
    expect = case["expect"]
    route = str(case["route"])
    want_hash = expect.get("hash") or ""
    want_q = expect.get("query_q")

    missing = sorted(REQUIRED_JOURNEY_KEYS - set(journeys))
    if missing:
        errors.append(f"route_journeys missing keys {missing}")
        return errors

    def _need_map(name: str) -> Mapping[str, Any] | None:
        payload = journeys.get(name)
        if not isinstance(payload, Mapping):
            errors.append(f"journey {name} is not an object: {payload!r}")
            return None
        if payload.get("ok") is not True:
            errors.append(f"journey {name} not ok: {payload!r}")
        return payload

    change = _need_map("change")
    if change is not None:
        if change.get("url_q") != "journeyprobe" or change.get("input") != "journeyprobe":
            errors.append(
                f"journey change did not apply journeyprobe URL/input: {change!r}"
            )
        count = change.get("visible_result_count")
        ids = change.get("visible_entry_ids")
        probe_ids = expected_ids_for_query("journeyprobe")
        if not isinstance(count, int) or not isinstance(ids, list) or set(ids) != set(probe_ids) or count != len(probe_ids):
            errors.append(
                f"journey change membership/count mismatch: count={count!r} "
                f"ids={ids!r} expected={probe_ids!r}"
            )

    clear = _need_map("clear")
    if clear is not None:
        if clear.get("url_q") not in (None, "") or clear.get("input") not in (None, ""):
            errors.append(f"journey clear left stale q/input: {clear!r}")
        count = clear.get("visible_result_count")
        ids = clear.get("visible_entry_ids")
        if (
            not isinstance(count, int)
            or not isinstance(ids, list)
            or set(ids) != set(full_library_ids)
            or count != len(full_library_ids)
        ):
            errors.append(
                f"journey clear did not restore full library: count={count!r} ids={ids!r}"
            )

    reload = _need_map("reload")
    if reload is not None:
        post_href = reload.get("post_href")
        if not _route_in_href(post_href, route):
            errors.append(f"journey reload post_href {post_href!r} does not match {route!r}")
        post_q = reload.get("post_q")
        if want_q is None:
            if post_q not in (None, ""):
                errors.append(f"journey reload resurrected query {post_q!r}")
        elif post_q != want_q:
            errors.append(f"journey reload post_q {post_q!r} != {want_q!r}")
        post_hash = reload.get("post_hash")
        want_hash_bare = want_hash.lstrip("#")
        if want_hash_bare:
            if str(post_hash).lstrip("#") != want_hash_bare:
                errors.append(f"journey reload post_hash {post_hash!r} != {want_hash!r}")
        elif post_hash not in (None, "", "#"):
            errors.append(f"journey reload unexpected hash {post_hash!r}")
        rehydrated = reload.get("input_rehydrated")
        expected_input = want_q or ""
        if rehydrated not in (expected_input, want_q):
            errors.append(
                f"journey reload input_rehydrated {rehydrated!r} != {expected_input!r}"
            )
        expected_reload_ids = (
            expected_ids_for_query(want_q) if want_q else list(full_library_ids)
        )
        reload_count = reload.get("visible_result_count")
        reload_ids = reload.get("visible_entry_ids")
        if (
            not isinstance(reload_count, int)
            or not isinstance(reload_ids, list)
            or set(reload_ids) != set(expected_reload_ids)
            or reload_count != len(expected_reload_ids)
        ):
            errors.append(
                f"journey reload membership/count mismatch: count={reload_count!r} "
                f"ids={reload_ids!r} expected={expected_reload_ids!r}"
            )

    back = _need_map("back")
    if back is not None:
        if back.get("performed") is not True:
            errors.append(f"journey back was not performed: {back!r}")
        after_href = back.get("after_href") or back.get("href")
        if not isinstance(after_href, str) or not after_href:
            errors.append(f"journey back missing after_href: {back!r}")
        if back.get("url_q") != back.get("input") and not (
            back.get("url_q") in (None, "") and back.get("input") in (None, "")
        ):
            errors.append(f"journey back URL/input disagree: {back!r}")
        if "navprobe" in str(after_href) or back.get("url_q") == "navprobe":
            errors.append(f"journey back remained on the probe URL: {back!r}")

    forward = _need_map("forward")
    if forward is not None:
        if forward.get("performed") is not True:
            errors.append(f"journey forward was not performed: {forward!r}")
        after_href = forward.get("after_href") or forward.get("href")
        if not isinstance(after_href, str) or not after_href:
            errors.append(f"journey forward missing after_href: {forward!r}")
        if forward.get("url_q") != "navprobe" or forward.get("input") != "navprobe":
            errors.append(f"journey forward did not rehydrate navprobe: {forward!r}")
        fwd_count = forward.get("visible_result_count")
        fwd_ids = forward.get("visible_entry_ids")
        probe_ids = expected_ids_for_query("navprobe")
        if (
            not isinstance(fwd_count, int)
            or not isinstance(fwd_ids, list)
            or set(fwd_ids) != set(probe_ids)
            or fwd_count != len(probe_ids)
        ):
            errors.append(
                f"journey forward membership/count mismatch: count={fwd_count!r} ids={fwd_ids!r}"
            )

    share = _need_map("share")
    if share is not None:
        href = share.get("href")
        final_href = share.get("final_href")
        if not _route_in_href(href, route):
            errors.append(f"journey share href {href!r} is not the exact share target for {route!r}")
        if want_q is None:
            if _href_query(href) not in (None, ""):
                errors.append(f"journey share href carried unexpected q: {href!r}")
        elif _href_query(href) != want_q:
            errors.append(f"journey share href q {_href_query(href)!r} != {want_q!r}")
        if want_hash:
            if _href_hash(href) != want_hash:
                errors.append(f"journey share href hash {_href_hash(href)!r} != {want_hash!r}")
        computed = bool(isinstance(href, str) and href and href == final_href)
        declared = share.get("matches_final")
        if declared is True and not computed:
            errors.append(
                f"journey share matches_final was asserted without href==final_href: {share!r}"
            )
        if not computed:
            errors.append(f"journey share href does not equal observed final_href: {share!r}")
    return errors


def _authenticate_binding(
    binding: Mapping[str, Any],
    *,
    repo_root: Path,
    tool_version: str | None,
) -> list[str]:
    errors: list[str] = []
    source_commit = binding.get("source_commit")
    source_tree = binding.get("source_tree")
    if not isinstance(source_commit, str) or not GIT_SHA_RE.fullmatch(source_commit):
        errors.append(
            f"candidate_binding.source_commit is not a 40-char git SHA: {source_commit!r}"
        )
        return errors
    if source_commit == "0" * 40:
        errors.append("candidate_binding.source_commit is a forged all-zero identity")
        return errors
    if not isinstance(source_tree, str) or not GIT_SHA_RE.fullmatch(source_tree):
        errors.append(
            f"candidate_binding.source_tree is not a 40-char git SHA: {source_tree!r}"
        )

    rc, kind = _git(repo_root, "cat-file", "-t", source_commit)
    if rc != 0 or kind != "commit":
        errors.append(
            f"candidate_binding.source_commit {source_commit} is not a commit in {repo_root}"
        )
        return errors
    rc, tree = _git(repo_root, "rev-parse", f"{source_commit}^{{tree}}")
    if rc != 0 or tree != source_tree:
        errors.append(
            f"candidate_binding.source_tree {source_tree!r} != "
            f"{source_commit}^{{tree}} {tree!r}"
        )

    rc, head = _git(repo_root, "rev-parse", "HEAD")
    if rc != 0 or not GIT_SHA_RE.fullmatch(head):
        errors.append("unable to resolve git HEAD for candidate identity")
        return errors
    rc_anc, _ = _git(repo_root, "merge-base", "--is-ancestor", source_commit, "HEAD")
    if rc_anc != 0:
        errors.append(
            f"source_commit {source_commit} is neither HEAD nor an ancestor of HEAD {head}"
        )

    site_path = repo_root / "site" / "reference.html"
    if site_path.is_file():
        actual = _sha256_file(site_path)
        declared = binding.get("site_reference_sha256")
        if actual != declared:
            errors.append(
                "site_reference_sha256 does not match site/reference.html bytes "
                f"(disk {actual} != declared {declared})"
            )
    else:
        errors.append("site/reference.html missing; cannot authenticate built artifact")

    tool_path = repo_root / "scripts" / "capture_page_evidence.py"
    if tool_path.is_file():
        actual_tool = _sha256_file(tool_path)
        declared_tool = binding.get("capture_tool_module_sha256")
        if actual_tool != declared_tool:
            errors.append(
                "capture_tool_module_sha256 does not match scripts/capture_page_evidence.py "
                f"(disk {actual_tool} != declared {declared_tool})"
            )
    declared_tool_version = binding.get("capture_tool_version")
    if declared_tool_version != tool_version:
        errors.append(
            f"candidate_binding.capture_tool_version {declared_tool_version!r} "
            f"!= manifest tool.version {tool_version!r}"
        )

    invocation = binding.get("render_invocation")
    if not isinstance(invocation, Mapping):
        errors.append("candidate_binding.render_invocation missing")
    else:
        command = invocation.get("command")
        argv = invocation.get("argv")
        inputs = invocation.get("input_digests")
        outputs = invocation.get("output_digests")
        if not isinstance(command, str) or "build_market_reference" not in command:
            errors.append(
                f"render_invocation.command does not name the market-reference builder: {command!r}"
            )
        if not isinstance(argv, list) or not argv:
            errors.append("render_invocation.argv missing")
        if not isinstance(inputs, Mapping):
            errors.append("render_invocation.input_digests missing")
        else:
            for rel in REQUIRED_RENDER_INPUTS:
                digest = inputs.get(rel)
                path = repo_root / rel
                if not isinstance(digest, str) or not digest:
                    errors.append(f"render_invocation.input_digests[{rel}] missing")
                elif path.is_file() and _sha256_file(path) != digest:
                    errors.append(
                        f"render_invocation.input_digests[{rel}] does not match disk bytes"
                    )
        if not isinstance(outputs, Mapping) or not outputs.get("site/reference.html"):
            errors.append("render_invocation.output_digests missing site/reference.html")
        elif outputs.get("site/reference.html") != binding.get("site_reference_sha256"):
            errors.append(
                "render_invocation.output_digests[site/reference.html] != site_reference_sha256"
            )

    assets = binding.get("shared_asset_digests")
    if not isinstance(assets, Mapping) or not assets:
        errors.append("candidate_binding.shared_asset_digests missing")
    else:
        for rel in REQUIRED_SHARED_ASSETS:
            if rel not in assets:
                errors.append(f"shared_asset_digests missing {rel}")
        for rel, digest in assets.items():
            if not isinstance(rel, str) or not isinstance(digest, str):
                errors.append(f"shared_asset_digests has a non-string entry {rel!r}")
                continue
            path = repo_root / rel
            if path.is_file() and _sha256_file(path) != digest:
                errors.append(f"shared_asset_digests[{rel}] does not match disk bytes")
    return errors


def validate_manifest_route_matrix(
    manifest: Mapping[str, Any],
    *,
    evidence_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Return human-readable defects; empty list means the 32-cell contract holds."""

    errors: list[str] = []
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    if not isinstance(manifest, Mapping):
        return ["manifest top level must be an object"]
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, got {manifest.get('schema')!r}")

    tool = manifest.get("tool") if isinstance(manifest.get("tool"), Mapping) else {}
    version_raw = tool.get("version") if isinstance(tool, Mapping) else None
    version = _parse_tool_version(version_raw)
    if version is None or version < MIN_TOOL_VERSION:
        errors.append(
            f"capture tool version must be >= {'.'.join(str(x) for x in MIN_TOOL_VERSION)}; "
            f"got {version_raw!r}"
        )

    binding = manifest.get("candidate_binding")
    if not isinstance(binding, Mapping):
        errors.append("missing candidate_binding (source/tree/site/serve/capture identity)")
        binding = {}
    else:
        for key in sorted(REQUIRED_BINDING_KEYS):
            val = binding.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"candidate_binding.{key} missing or empty")
        errors.extend(
            _authenticate_binding(
                binding, repo_root=root, tool_version=version_raw if isinstance(version_raw, str) else None
            )
        )

    full_library_ids = expected_query_entry_ids(None, repo_root=root)
    expected_curve_ids = expected_query_entry_ids("curve", repo_root=root)

    def ids_for_query(query: str) -> list[str]:
        return expected_query_entry_ids(query, repo_root=root)

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        return errors + ["manifest.pages must be a non-empty list"]

    page_ids: list[Any] = []
    routes: list[Any] = []
    for page in pages:
        if not isinstance(page, Mapping):
            errors.append("manifest.pages contains a non-object entry")
            continue
        page_ids.append(page.get("page_id"))
        routes.append(page.get("route"))
        pid = page.get("page_id")
        route = page.get("route")
        if pid not in REQUIRED_PAGE_IDS:
            errors.append(f"unexpected extra page {pid!r} route {route!r}")
        elif route not in REQUIRED_ROUTE_SET:
            errors.append(f"page {pid!r} has unexpected route {route!r}")
    for pid in {p for p in page_ids if page_ids.count(p) > 1}:
        errors.append(f"duplicate page_id {pid!r}")
    for route in {r for r in routes if routes.count(r) > 1}:
        errors.append(f"duplicate route row {route!r}")
    required_present = [p for p in page_ids if p in REQUIRED_PAGE_IDS]
    if len(required_present) != len(REQUIRED_PAGE_IDS):
        missing_ids = sorted(REQUIRED_PAGE_IDS - set(required_present))
        if missing_ids:
            errors.append(f"missing required page_ids {missing_ids}")

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

        for key in ("console_errors", "failed_responses"):
            bag = page.get(key) or []
            if isinstance(bag, list) and bag:
                errors.append(f"page {page_id!r}: unexpected {key}: {bag!r}")

        journeys = page.get("route_journeys")
        if case["expect"].get("require_journeys"):
            if not isinstance(journeys, Mapping):
                errors.append(f"page {page_id!r}: missing route_journeys")
            else:
                errors.extend(
                    f"page {page_id!r}: {err}"
                    for err in _validate_journeys(
                        case,
                        journeys,
                        expected_ids_for_query=ids_for_query,
                        full_library_ids=full_library_ids,
                    )
                )

        states = page.get("states")
        if not isinstance(states, list):
            errors.append(f"page {page_id!r}: states must be a list")
            continue
        present: set[tuple[str, str, str]] = set()
        for state in states:
            if not isinstance(state, Mapping):
                errors.append(f"page {page_id!r}: non-object state entry")
                continue
            key = _rest_key(state)
            if key is None:
                continue
            viewport, locale, theme = key
            if (
                viewport not in ALLOWED_VIEWPORTS
                or locale not in ALLOWED_LOCALES
                or theme not in ALLOWED_THEMES
            ):
                errors.append(
                    f"page {page_id!r}: unexpected extra REST cell {key} "
                    "(closed set is desktop/mobile × en/zh × dark/light)"
                )
                continue
            logical_keys.append((page_id, viewport, locale, theme))
            if not state.get("captured"):
                errors.append(f"page {page_id!r} cell {key}: not captured")
                continue
            present.add(key)
            sha = state.get("sha256")
            if isinstance(sha, str) and sha:
                digest_owners.setdefault(sha, set()).add(str(route))
            file_name = state.get("file")
            if isinstance(file_name, str) and file_name:
                manifest_files.add(Path(file_name).name)
            route_errs = _validate_route_state(
                case,
                state,
                full_library_ids=full_library_ids,
                expected_curve_ids=expected_curve_ids,
            )
            errors.extend(f"page {page_id!r} cell {key}: {err}" for err in route_errs)
            if "unknown_state" in state and state.get("unknown_state"):
                errors.append(f"page {page_id!r} cell {key}: unknown_state flagged")
        missing = sorted(REQUIRED_REST_KEYS - present)
        if missing:
            errors.append(f"page {page_id!r}: missing REST cells {missing}")
        extra = sorted(present - REQUIRED_REST_KEYS)
        if extra:
            errors.append(f"page {page_id!r}: unexpected extra REST cells {extra}")

    for logical in {k for k in logical_keys if logical_keys.count(k) > 1}:
        errors.append(f"duplicate logical cell {logical!r}")

    for sha, routes_hit in digest_owners.items():
        if len(routes_hit) > 1:
            errors.append(
                f"screenshot digest {sha[:16]}… reused across distinct routes {sorted(routes_hit)} "
                "without per-route isolation"
            )

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

    return errors


def _validate_route_state(
    case: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    full_library_ids: Sequence[str],
    expected_curve_ids: Sequence[str],
) -> list[str]:
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

    count = rs.get("visible_result_count")
    ids = rs.get("visible_entry_ids")
    expected_ids: Sequence[str] | None = None
    if expect.get("require_membership"):
        expected_ids = expected_curve_ids
    elif expect.get("require_full_library"):
        expected_ids = full_library_ids
    if expected_ids is not None:
        if not isinstance(ids, list):
            errors.append("visible_entry_ids missing or not a list")
        elif set(ids) != set(expected_ids):
            errors.append(
                f"visible_entry_ids {ids!r} != subject-derived {list(expected_ids)!r}"
            )
        if not isinstance(count, int) or count != len(expected_ids):
            errors.append(
                f"visible_result_count {count!r} != subject-derived {len(expected_ids)}"
            )

    min_results = expect.get("min_visible_results")
    if isinstance(min_results, int):
        if not isinstance(count, int) or count < min_results:
            errors.append(
                f"visible_result_count {count!r} < required minimum {min_results}"
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
            if expected_ids is not None and isinstance(label, str):
                total = len(full_library_ids)
                # A 34/34 label is only lawful when the subject actually shows 34.
                if re.search(rf"\b{total}\s+of\s+{total}\b", label) and count != total:
                    errors.append(
                        f"count label {label!r} claims a full {total}/{total} library "
                        f"but visible_result_count is {count}"
                    )

    if expect.get("require_focus"):
        focused = rs.get("focused_element_id")
        if focused != want_sel:
            errors.append(
                f"focused_element_id {focused!r} is not the required focus target {want_sel!r}"
            )
        if not rs.get("focused_visible"):
            errors.append("focused_visible is false for valid-anchor case")
        if rs.get("target_below_fixed_ui") is not True:
            errors.append(
                f"target_below_fixed_ui {rs.get('target_below_fixed_ui')!r} is not true"
            )

    requested = rs.get("requested_url")
    final = rs.get("final_url")
    if not isinstance(requested, str) or not requested:
        errors.append("requested_url missing")
    if not isinstance(final, str) or not final:
        errors.append("final_url missing")
    route = str(case["route"])
    if isinstance(final, str) and not _route_in_href(final, route):
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
