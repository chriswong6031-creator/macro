"""MOR-1 route-semantic evidence contract (companion to the generic 8-cell gate).

The fleet checker ``scripts/check_ui_visual_evidence.py`` proves mechanical REST
coverage (desktop/mobile × en/zh × dark/light) per ``manifest.pages[]`` row. It
does not prove route semantics. This module owns the frozen 4 route-case × 8
REST = 32-cell acceptance matrix for Market Reference and rejects the historical
false-complete pattern (one default-route page + three ``excluded`` rows).

No second screenshot plane: it reads the existing ``mastermind.p0_evidence.v2``
manifest the capture harness already writes, plus per-state ``route_state``
fields, per-cell console/response receipts, one axes-bound ``route_journey``,
and ``candidate_binding``.

Identity rule of this module: **nothing is authenticated against the current
disk.** Every bound path is compared to the blob it had in the declared subject
commit, so a dirty worktree, a rebuilt artifact, or a self-consistent set of
current-disk hashes cannot stand in for a clean immutable subject.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import subprocess
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, parse_qsl, urlparse

SCHEMA = "mastermind.p0_evidence.v2"
MIN_TOOL_VERSION = (1, 6, 0)
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Mirrors templates/reference.html.j2 ``normalize()``.
_JS_STRIP = re.compile(r"[\s　-〿＀-￯!-\/:-@\[-`{-~]")

REPO_ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_DIR_REL = "mockups/evidence/market_reference_mor1"

ALLOWED_VIEWPORTS = frozenset({"desktop", "mobile"})
ALLOWED_LOCALES = frozenset({"en", "zh"})
ALLOWED_THEMES = frozenset({"dark", "light"})
REQUIRED_ACCESS = "anonymous"

# Non-evidence paths this packet binds. A change to any of them after the
# subject commit invalidates the packet, so the evidence descendant must not
# touch them.
OWNED_SOURCE_PATHS: tuple[str, ...] = (
    "templates/reference.html.j2",
    "config/market_reference.yml",
    "site/reference.html",
    "scripts/build_market_reference.py",
    "scripts/capture_page_evidence.py",
    "scripts/capture_market_reference_mor1.py",
    "scripts/market_reference_route_evidence.py",
    "scripts/check_market_reference_route_evidence.py",
    "tests/test_market_reference.py",
)

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
            "require_count_label": True,
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
            "require_count_label": True,
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
            "require_count_label": True,
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
        "pathname",
        "search",
        "hash",
        "query_q",
        "rf_q_value",
        "miss_visible",
        "miss_q_text",
        "selected_id",
        "visible_result_count",
        "visible_entry_ids",
        "count_label_visible",
        "count_label_text",
        "count_label_numerator",
        "count_label_denominator",
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
        "site_dir",
        "capture_tool_version",
        "capture_tool_module_sha256",
        "verifier_module_sha256",
    }
)

REQUIRED_RENDER_INPUTS = ("templates/reference.html.j2", "config/market_reference.yml")

# The render is frozen by exact shape, not by "the string mentions the builder".
RENDER_MODULE = "scripts.build_market_reference"
RENDER_COMMAND = "python -m scripts.build_market_reference"
_PYTHON_EXE_RE = re.compile(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?$")

# One axes-bound journey per page. ``initial``/``pre_push``/``pushed`` are
# context steps; the rest are the proven transitions.
REQUIRED_JOURNEY_STEPS = frozenset(
    {
        "initial",
        "change",
        "empty_probe",
        "clear",
        "pre_push",
        "pushed",
        "back",
        "forward",
        "reload",
        "share",
    }
)
REQUIRED_JOURNEY_AXES = frozenset(
    {"viewport", "viewport_width", "viewport_height", "locale", "theme", "access", "force_state"}
)

# The old hard-coded seven. Retained only as a floor: the authoritative set is
# derived from the rendered page (``local_asset_digests``), so an asset the page
# actually loads can never be silently omitted from the receipt.
REQUIRED_SHARED_ASSETS = (
    "site/theme.css",
    "site/navigation-refresh.css",
    "site/theme.js",
    "site/logo_config.js",
    "site/stock-logos.js",
    "site/live_config.js",
    "site/live.js",
)

_LOCAL_ASSET_RE = re.compile(
    r"""<(?:script[^>]*\ssrc|link[^>]*\shref)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
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


@lru_cache(maxsize=512)
def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Read-only git query, memoized for the life of the process.

    Every call costs ~2s in the production clone (9.9 MB index, blobless
    promisor remote), and a validation asks the same questions repeatedly, so
    an uncached helper turned one test module into a multi-minute run.
    """

    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout or "").strip()


@lru_cache(maxsize=64)
def _git_blob_sha256_batch(
    repo: Path, commit: str, rels: tuple[str, ...]
) -> tuple[tuple[str, str | None], ...]:
    """sha256 of every ``rel`` as of ``commit``, in ONE ``cat-file --batch``.

    Never reads the working tree: a dirty file, a rebuilt artifact, or a set of
    self-consistent current-disk hashes cannot stand in for a committed blob.
    """

    if not rels:
        return ()
    payload = "".join(f"{commit}:{rel}\n" for rel in rels).encode()
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=payload,
        capture_output=True,
        check=False,
    )
    out = proc.stdout or b""
    results: list[tuple[str, str | None]] = []
    pos = 0
    for rel in rels:
        nl = out.find(b"\n", pos)
        if nl < 0:
            results.append((rel, None))
            continue
        header = out[pos:nl].decode("utf-8", "replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            # "<input> missing" / "<input> ambiguous" — no content follows.
            results.append((rel, None))
            continue
        size = int(parts[2])
        data = out[pos : pos + size]
        pos += size + 1  # trailing newline
        results.append((rel, hashlib.sha256(data).hexdigest()))
    return tuple(results)


@lru_cache(maxsize=64)
def _git_blob(repo: Path, commit: str, rel: str) -> bytes | None:
    """Bytes of ``rel`` as of ``commit`` — never the current working tree."""

    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", f"{commit}:{rel}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def derive_local_assets(html: str) -> list[str]:
    """Same-origin script/stylesheet dependencies of the rendered page.

    Derived from the page itself so a receipt can never cover a hard-coded
    subset while the page quietly loads something else. Absolute and
    protocol-relative URLs are cross-origin and are not repo blobs.
    """

    found: list[str] = []
    for raw in _LOCAL_ASSET_RE.findall(html or ""):
        ref = str(raw).strip()
        if not ref or ref.startswith(("http://", "https://", "//", "data:", "#", "mailto:")):
            continue
        ref = ref.split("?", 1)[0].split("#", 1)[0]
        if not ref:
            continue
        rel = f"site/{ref.lstrip('./').lstrip('/')}"
        if rel not in found:
            found.append(rel)
    return sorted(found)


@lru_cache(maxsize=8)
def _registry_search_index(repo_root: Path) -> tuple[tuple[str, str], ...]:
    """``(id, search_key)`` in registry order."""

    from scripts.build_market_reference import load_registry, search_key

    raw = load_registry(repo_root / "config" / "market_reference.yml")
    return tuple(
        (str(entry.get("id")), search_key(entry))
        for entry in (raw.get("entries") or [])
        if entry.get("id")
    )


_RF_ENTRY_RE = re.compile(
    r"""<article\b(?=[^>]*\bclass="[^"]*\brf-e\b)[^>]*\bid="([^"]+)\"""",
    re.IGNORECASE,
)


def rendered_entry_order(html: str) -> list[str]:
    """Entry ids in the order the SERVER-RENDERED page lays them out.

    Registry order is NOT DOM order — the builder groups entries into families,
    so the page emits a different sequence (measured: the two disagree from the
    4th entry on). Order therefore comes from the rendered artifact, which is
    itself digest-authenticated against the subject commit, while membership
    still comes from the registry predicate. A filter that reorders or drops
    rows fails against the pair; neither alone would catch it.
    """

    seen: list[str] = []
    for eid in _RF_ENTRY_RE.findall(html or ""):
        if eid not in seen:
            seen.append(eid)
    return seen


def expected_query_entry_ids(
    query: str | None,
    *,
    repo_root: Path,
    dom_order: Sequence[str] | None = None,
) -> list[str]:
    """Exact ORDERED visible-id list under the page's ``data-search`` predicate.

    Duplicate-free by construction (entry ids are unique).
    """

    index = dict(_registry_search_index(repo_root))
    if dom_order is None:
        page = repo_root / "site" / "reference.html"
        dom_order = (
            rendered_entry_order(page.read_text(encoding="utf-8", errors="replace"))
            if page.is_file()
            else list(index)
        )
    order = [eid for eid in dom_order if eid in index]
    qn = js_normalize_query(query or "")
    if not qn:
        return order
    return [eid for eid in order if qn in index[eid]]


# Probe tokens for the journey. They are validated against the registry at
# capture and at validation time: ``change``/``forward`` must select a real,
# non-empty, strict subset of the library, and ``empty`` must select nothing.
# The retired ``journeyprobe``/``navprobe`` pair matched nothing, so a handler
# that hid every row satisfied both and the interaction proved nothing.
PROBE_CHANGE = "regime"
PROBE_FORWARD = "yield"
PROBE_EMPTY = "zzzznotathing"


def resolve_probe_queries(
    repo_root: Path, *, dom_order: Sequence[str] | None = None
) -> dict[str, Any]:
    """Registry-derived probe queries plus their expected ordered id lists."""

    def ids(q: str | None) -> list[str]:
        return expected_query_entry_ids(q, repo_root=repo_root, dom_order=dom_order)

    full = ids(None)
    change = ids(PROBE_CHANGE)
    forward = ids(PROBE_FORWARD)
    empty = ids(PROBE_EMPTY)
    return {
        "change_query": PROBE_CHANGE,
        "forward_query": PROBE_FORWARD,
        "empty_query": PROBE_EMPTY,
        "change_ids": change,
        "forward_ids": forward,
        "empty_ids": empty,
        "full_ids": full,
    }


def _probe_sanity(probes: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    full = list(probes["full_ids"])
    for name in ("change", "forward"):
        ids = list(probes[f"{name}_ids"])
        if not ids:
            errors.append(
                f"probe query {probes[f'{name}_query']!r} selects nothing; a zero-result "
                "probe cannot discriminate a handler that hides every row"
            )
        elif len(ids) >= len(full):
            errors.append(
                f"probe query {probes[f'{name}_query']!r} selects the whole library; "
                "it cannot discriminate a filter that never runs"
            )
    if probes["empty_ids"]:
        errors.append(
            f"negative probe {probes['empty_query']!r} unexpectedly selects "
            f"{probes['empty_ids']!r}"
        )
    if probes["change_ids"] == probes["forward_ids"]:
        errors.append("change and forward probes select the same set; they cannot be told apart")
    return errors


# ---------------------------------------------------------------------------
# exact route parsing
# ---------------------------------------------------------------------------


def parse_route(route: str) -> tuple[str, str | None, str]:
    """``reference.html?q=curve`` -> (``/reference.html``, ``curve``, ``''``)."""

    parsed = urlparse(route)
    path = parsed.path or ""
    if not path.startswith("/"):
        path = "/" + path
    q = (parse_qs(parsed.query).get("q") or [None])[0]
    frag = f"#{parsed.fragment}" if parsed.fragment else ""
    return path, q, frag


def parse_href(href: Any) -> tuple[str, str | None, str] | None:
    if not isinstance(href, str) or not href:
        return None
    try:
        parsed = urlparse(href)
    except Exception:
        return None
    path = parsed.path or ""
    if not path.startswith("/"):
        path = "/" + path
    q = (parse_qs(parsed.query).get("q") or [None])[0]
    frag = f"#{parsed.fragment}" if parsed.fragment else ""
    return path, q, frag


def _origin_of(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def canonical_search(query: str | None) -> str:
    return f"?q={query}" if query else ""


def _validate_url(
    url: Any,
    *,
    label: str,
    expect_path: str,
    expect_q: str | None,
    expect_hash: str,
    origin: str | None,
) -> list[str]:
    """Closed URL identity: origin, pathname, EXACT query multiset, fragment.

    Substring matching is retired (``…?q=navprobe`` contains ``reference.html``
    and used to pass as the route). So is per-key ``parse_qs`` lookup, which
    silently tolerated extra keys, a duplicated ``q``, and a blank ``?q=`` on a
    route whose query must be absent. The query is compared as an ordered list
    of pairs with blanks kept, so all three are caught. A cross-origin URL is
    rejected outright: evidence must come from the capture's own loopback
    server, never from production or a third party.
    """

    errors: list[str] = []
    if not isinstance(url, str) or not url:
        return [f"{label} is missing: {url!r}"]
    try:
        parsed = urlparse(url)
    except Exception:
        return [f"{label} is unparseable: {url!r}"]
    got_origin = _origin_of(url)
    if origin is not None:
        if got_origin is None:
            errors.append(f"{label} {url!r} has no absolute origin; expected {origin}")
        elif got_origin != origin:
            errors.append(
                f"{label} origin {got_origin!r} != capture serve_root {origin!r} "
                "(cross-origin evidence URL)"
            )
    path = parsed.path or ""
    if not path.startswith("/"):
        path = "/" + path
    if path != expect_path:
        errors.append(f"{label} pathname {path!r} != expected {expect_path!r}")
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    want_pairs = [] if expect_q is None else [("q", expect_q)]
    if pairs != want_pairs:
        errors.append(f"{label} query {pairs!r} != expected exactly {want_pairs!r}")
    frag = f"#{parsed.fragment}" if parsed.fragment else ""
    if frag != expect_hash:
        errors.append(f"{label} hash {frag!r} != expected {expect_hash!r}")
    return errors


def _validate_recorded_url(
    payload: Mapping[str, Any],
    *,
    label: str,
    expect_path: str,
    expect_q: str | None,
    expect_hash: str,
    origin: str | None,
    href_key: str = "href",
) -> list[str]:
    """Validate a recorded URL AND the parsed fields recorded beside it.

    A step that reports ``pathname``/``search``/``hash``/``url_q`` disagreeing
    with its own ``href`` is self-inconsistent, so both are checked against the
    same expectation rather than trusting either.
    """

    errors = _validate_url(
        payload.get(href_key),
        label=f"{label} {href_key}",
        expect_path=expect_path,
        expect_q=expect_q,
        expect_hash=expect_hash,
        origin=origin,
    )
    if "pathname" in payload and str(payload.get("pathname") or "") != expect_path:
        errors.append(f"{label} pathname field {payload.get('pathname')!r} != {expect_path!r}")
    if "search" in payload:
        want_search = canonical_search(expect_q)
        if str(payload.get("search") or "") != want_search:
            errors.append(f"{label} search field {payload.get('search')!r} != {want_search!r}")
    if "hash" in payload and str(payload.get("hash") or "") != expect_hash:
        errors.append(f"{label} hash field {payload.get('hash')!r} != {expect_hash!r}")
    if "url_q" in payload:
        got_q = payload.get("url_q")
        got_q = got_q if isinstance(got_q, str) and got_q else None
        if got_q != expect_q:
            errors.append(f"{label} url_q field {got_q!r} != {expect_q!r}")
    return errors


def _route_matches(href: Any, route: str, *, label: str, origin: str | None = None) -> list[str]:
    want_path, want_q, want_hash = parse_route(route)
    return _validate_url(
        href,
        label=label,
        expect_path=want_path,
        expect_q=want_q,
        expect_hash=want_hash,
        origin=origin,
    )


def _exact_membership(
    payload: Mapping[str, Any],
    expected: Sequence[str],
    *,
    label: str,
    full_total: int,
    require_count_label: bool = True,
) -> list[str]:
    """Ordered, duplicate-free membership plus a two-number count label.

    Set equality is retired: ``[a, b, a]`` with ``count=2`` used to satisfy an
    expectation of ``[a, b]``. So did a label reading ``3 of 99`` beside three
    visible rows.
    """

    errors: list[str] = []
    ids = payload.get("visible_entry_ids")
    count = payload.get("visible_result_count")
    want = list(expected)
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        errors.append(f"{label} visible_entry_ids missing or not a list of strings: {ids!r}")
        return errors
    if len(set(ids)) != len(ids):
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        errors.append(f"{label} visible_entry_ids contains duplicates {dupes}")
    if ids != want:
        errors.append(f"{label} visible_entry_ids {ids!r} != subject-derived ordered {want!r}")
    if not isinstance(count, int) or count != len(want):
        errors.append(f"{label} visible_result_count {count!r} != subject-derived {len(want)}")
    elif count != len(ids):
        errors.append(
            f"{label} visible_result_count {count} != len(visible_entry_ids) {len(ids)}"
        )
    if require_count_label:
        numerator = payload.get("count_label_numerator")
        denominator = payload.get("count_label_denominator")
        if numerator != len(want):
            errors.append(
                f"{label} count label numerator {numerator!r} != visible count {len(want)}"
            )
        if denominator != full_total:
            errors.append(
                f"{label} count label denominator {denominator!r} != full library {full_total}"
            )
    return errors


# ---------------------------------------------------------------------------
# journey
# ---------------------------------------------------------------------------


def _validate_journey(
    case: Mapping[str, Any],
    journey: Mapping[str, Any],
    *,
    probes: Mapping[str, Any],
    origin: str | None,
) -> list[str]:
    errors: list[str] = []
    expect = case["expect"]
    route = str(case["route"])
    want_path, want_q, want_hash = parse_route(route)
    full_ids = list(probes["full_ids"])
    full_total = len(full_ids)
    case_ids = (
        expected_query_entry_ids_cached(want_q, probes) if want_q else full_ids
    )

    axes = journey.get("axes")
    if not isinstance(axes, Mapping):
        errors.append("route_journey.axes missing — an unscoped journey receipt owns no cell")
        return errors
    missing_axes = sorted(REQUIRED_JOURNEY_AXES - set(axes))
    if missing_axes:
        errors.append(f"route_journey.axes missing {missing_axes}")
    if axes.get("access") != REQUIRED_ACCESS:
        errors.append(f"route_journey.axes.access {axes.get('access')!r} != {REQUIRED_ACCESS!r}")
    if axes.get("force_state") is not None:
        errors.append(f"route_journey.axes.force_state {axes.get('force_state')!r} is not null")
    if axes.get("viewport") not in ALLOWED_VIEWPORTS:
        errors.append(f"route_journey.axes.viewport {axes.get('viewport')!r} is not a frozen viewport")
    if axes.get("locale") not in ALLOWED_LOCALES:
        errors.append(f"route_journey.axes.locale {axes.get('locale')!r} is not a frozen locale")
    if axes.get("theme") not in ALLOWED_THEMES:
        errors.append(f"route_journey.axes.theme {axes.get('theme')!r} is not a frozen theme")

    applied = journey.get("applied")
    if not isinstance(applied, Mapping):
        errors.append("route_journey.applied missing — requested axes are not proof of applied axes")
    else:
        for key in ("locale", "theme"):
            if applied.get(key) != axes.get(key):
                errors.append(
                    f"route_journey applied {key} {applied.get(key)!r} != requested {axes.get(key)!r}"
                )
        for key in ("viewport_width", "viewport_height"):
            if applied.get(key) != axes.get(key):
                errors.append(
                    f"route_journey applied {key} {applied.get(key)!r} != requested {axes.get(key)!r}"
                )

    for bag_name in ("console_errors", "failed_responses"):
        bag = journey.get(bag_name)
        if not isinstance(bag, list):
            errors.append(f"route_journey.{bag_name} missing — journey failures would be invisible")
        elif bag:
            errors.append(f"route_journey.{bag_name} not empty: {bag!r}")

    declared_probes = journey.get("probes")
    if not isinstance(declared_probes, Mapping):
        errors.append("route_journey.probes missing")
    else:
        for key in ("change_query", "forward_query", "empty_query"):
            if declared_probes.get(key) != probes[key]:
                errors.append(
                    f"route_journey.probes.{key} {declared_probes.get(key)!r} != "
                    f"registry-derived {probes[key]!r}"
                )

    steps = journey.get("steps")
    if not isinstance(steps, Mapping):
        errors.append("route_journey.steps missing")
        return errors
    missing = sorted(REQUIRED_JOURNEY_STEPS - set(steps))
    if missing:
        errors.append(f"route_journey.steps missing {missing}")
        return errors

    def step(name: str) -> Mapping[str, Any] | None:
        payload = steps.get(name)
        if not isinstance(payload, Mapping):
            errors.append(f"journey step {name} is not an object: {payload!r}")
            return None
        return payload

    def route_of(payload: Mapping[str, Any]) -> tuple[str, str | None, str]:
        q = payload.get("url_q")
        return (
            str(payload.get("pathname") or ""),
            q if isinstance(q, str) and q else None,
            str(payload.get("hash") or ""),
        )

    # Every step's pathname/query/hash is bound EXACTLY, href included. Binding
    # only the fields a step happened to be asked about let `change.hash=#stale`
    # and `empty_probe.url_q=<a real query>` validate with zero errors.
    #
    # The hash is empty on every post-interaction step: the page clears
    # location.hash when a search interaction dismisses the open entry
    # (close-affordance replaceState in templates/reference.html.j2), and it
    # returns on `reload` and `share`, which are fresh loads of the route.
    step_contract: dict[str, tuple[str, str | None, str]] = {
        "initial": (want_path, want_q, want_hash),
        "change": (want_path, probes["change_query"], ""),
        "empty_probe": (want_path, probes["empty_query"], ""),
        "clear": (want_path, None, ""),
        "pre_push": (want_path, want_q, ""),
        "pushed": (want_path, probes["forward_query"], ""),
        "back": (want_path, want_q, ""),
        "forward": (want_path, probes["forward_query"], ""),
        "reload": (want_path, want_q, want_hash),
    }
    for name, (exp_path, exp_q, exp_hash) in step_contract.items():
        payload = steps.get(name)
        if not isinstance(payload, Mapping):
            continue
        errors.extend(
            _validate_recorded_url(
                payload,
                label=f"journey {name}",
                expect_path=exp_path,
                expect_q=exp_q,
                expect_hash=exp_hash,
                origin=origin,
            )
        )

    initial = step("initial")
    if initial is not None:
        errors.extend(
            _exact_membership(initial, case_ids, label="journey initial", full_total=full_total)
        )

    change = step("change")
    if change is not None:
        if change.get("input") != probes["change_query"]:
            errors.append(
                f"journey change input {change.get('input')!r} != {probes['change_query']!r}"
            )
        errors.extend(
            _exact_membership(
                change,
                list(probes["change_ids"]),
                label="journey change",
                full_total=full_total,
            )
        )

    empty_probe = step("empty_probe")
    if empty_probe is not None:
        if empty_probe.get("input") != probes["empty_query"]:
            errors.append(
                f"journey empty_probe input {empty_probe.get('input')!r} != {probes['empty_query']!r}"
            )
        errors.extend(
            _exact_membership(
                empty_probe,
                [],
                label="journey empty_probe",
                full_total=full_total,
                require_count_label=False,
            )
        )

    clear = step("clear")
    if clear is not None:
        if clear.get("input") not in (None, ""):
            errors.append(f"journey clear left a stale input: {clear.get('input')!r}")
        errors.extend(
            _exact_membership(clear, full_ids, label="journey clear", full_total=full_total)
        )

    pre_push = step("pre_push")
    pushed = step("pushed")
    if pre_push is not None:
        got = route_of(pre_push)
        # The hash is expected EMPTY here, and that is a measured product
        # behavior rather than a loosened check: the page deliberately clears
        # location.hash when a search interaction dismisses the open entry
        # (templates/reference.html.j2, close-affordance replaceState), and the
        # journey always runs change -> empty_probe -> clear before this step.
        # `back` is then held to this exact state, hash included.
        want_pre = (want_path, want_q, "")
        if got != want_pre:
            errors.append(
                f"journey pre_push route {got!r} != the post-interaction route "
                f"{want_pre!r} (path and query of the route under test, hash dismissed "
                "by the search interaction)"
            )
        errors.extend(
            _exact_membership(pre_push, case_ids, label="journey pre_push", full_total=full_total)
        )

    back = step("back")
    if back is not None:
        if back.get("performed") is not True:
            errors.append(f"journey back was not performed: {back!r}")
        if pre_push is not None:
            got = route_of(back)
            want = route_of(pre_push)
            if got != want:
                errors.append(
                    f"journey back route {got!r} != the exact pre-push route {want!r}"
                )
            if back.get("input") != pre_push.get("input"):
                errors.append(
                    f"journey back input {back.get('input')!r} != pre-push "
                    f"{pre_push.get('input')!r}"
                )
        if back.get("url_q") == probes["forward_query"]:
            errors.append("journey back remained on the forward probe URL")
        errors.extend(
            _exact_membership(back, case_ids, label="journey back", full_total=full_total)
        )

    forward = step("forward")
    if forward is not None:
        if forward.get("performed") is not True:
            errors.append(f"journey forward was not performed: {forward!r}")
        if forward.get("input") != probes["forward_query"]:
            errors.append(
                f"journey forward input {forward.get('input')!r} != "
                f"{probes['forward_query']!r} (URL moved but the field did not rehydrate)"
            )
        if pre_push is not None:
            if str(forward.get("pathname") or "") != str(pre_push.get("pathname") or ""):
                errors.append(
                    f"journey forward pathname {forward.get('pathname')!r} != "
                    f"{pre_push.get('pathname')!r}"
                )
            if str(forward.get("hash") or "") != str(pre_push.get("hash") or ""):
                errors.append(
                    f"journey forward hash {forward.get('hash')!r} != {pre_push.get('hash')!r}"
                )
        errors.extend(
            _exact_membership(
                forward,
                list(probes["forward_ids"]),
                label="journey forward",
                full_total=full_total,
            )
        )

    reload_step = step("reload")
    if reload_step is not None:

        if reload_step.get("input") != (want_q or ""):
            errors.append(
                f"journey reload input {reload_step.get('input')!r} != rehydrated {want_q or ''!r}"
            )
        errors.extend(
            _exact_membership(reload_step, case_ids, label="journey reload", full_total=full_total)
        )

    share = step("share")
    if share is not None:
        href = share.get("href")
        errors.extend(_route_matches(href, route, label="journey share", origin=origin))
        final_href = share.get("final_href")
        # Recomputed here from the two recorded URLs — the declared flag is never
        # trusted, and the two URLs must come from a real reopen, not from
        # ``final_href = href``.
        parsed_href = parse_href(href)
        parsed_final = parse_href(final_href)
        # Origin is part of the round trip: a share URL that reopens the right
        # path/query/hash on the WRONG host has not round-tripped.
        computed = bool(
            parsed_href is not None
            and parsed_href == parsed_final
            and _origin_of(href) is not None
            and _origin_of(href) == _origin_of(final_href)
        )
        if share.get("matches_final") is not True:
            errors.append(
                f"journey share.matches_final is not exactly true: {share.get('matches_final')!r}"
            )
        if not computed:
            errors.append(
                f"journey share href {href!r} did not round-trip to final_href {final_href!r}"
            )
        reopened = share.get("reopened")
        if not isinstance(reopened, Mapping):
            errors.append(
                "journey share.reopened missing — a share URL that is never reopened "
                "proves only self-equality, not that the route rehydrates"
            )
        else:
            errors.extend(
                _route_matches(
                    reopened.get("final_href"),
                    route,
                    label="journey share.reopened",
                    origin=origin,
                )
            )
            if reopened.get("input") != (want_q or ""):
                errors.append(
                    f"journey share.reopened input {reopened.get('input')!r} != {want_q or ''!r}"
                )
            if bool(reopened.get("miss_visible")) != bool(expect.get("miss_visible")):
                errors.append(
                    f"journey share.reopened miss_visible {reopened.get('miss_visible')!r} != "
                    f"{expect.get('miss_visible')!r}"
                )
            want_sel = expect.get("selected_id")
            got_sel = reopened.get("selected_id") or None
            if got_sel != want_sel:
                errors.append(
                    f"journey share.reopened selected_id {got_sel!r} != {want_sel!r}"
                )
            if expect.get("require_focus"):
                if reopened.get("focused_element_id") != want_sel:
                    errors.append(
                        f"journey share.reopened focused_element_id "
                        f"{reopened.get('focused_element_id')!r} != {want_sel!r}"
                    )
                if reopened.get("target_below_fixed_ui") is not True:
                    errors.append(
                        "journey share.reopened target_below_fixed_ui is not true"
                    )
            for bag_name in ("console_errors", "failed_responses"):
                bag = reopened.get(bag_name)
                if not isinstance(bag, list):
                    errors.append(f"journey share.reopened.{bag_name} missing")
                elif bag:
                    errors.append(f"journey share.reopened.{bag_name} not empty: {bag!r}")
            errors.extend(
                _exact_membership(
                    reopened, case_ids, label="journey share.reopened", full_total=full_total
                )
            )
    return errors


def expected_query_entry_ids_cached(query: str | None, probes: Mapping[str, Any]) -> list[str]:
    """Case-route ids, reusing the already-computed registry views where possible."""

    if query is None:
        return list(probes["full_ids"])
    if query == probes["change_query"]:
        return list(probes["change_ids"])
    if query == probes["forward_query"]:
        return list(probes["forward_ids"])
    key = f"case_ids::{query}"
    if key in probes:
        return list(probes[key])
    return list(probes.get("_case_ids", {}).get(query, []))


# ---------------------------------------------------------------------------
# candidate binding
# ---------------------------------------------------------------------------


# Paths the builder needs in a replay checkout. Deliberately narrow: this is a
# rebuild of one page, not a clone.
REPLAY_TREES = ("scripts", "config", "templates", "lib")


@lru_cache(maxsize=16)
def _replay_render(
    repo_root: Path,
    source_commit: str,
    interpreter: str,
    clock: str,
) -> tuple[int, str, str]:
    """Rebuild ``site/reference.html`` from the SUBJECT COMMIT in a fresh tree.

    ``git archive`` gives a clean checkout of the immutable subject without
    touching the repo's worktree registry or the caller's working tree. Returns
    ``(returncode, digest, detail)``; digest is '' when the build produced no
    page.
    """

    import tempfile

    with tempfile.TemporaryDirectory(prefix="mor1-replay-") as tmp:
        root = Path(tmp)
        archive = subprocess.run(
            ["git", "-C", str(repo_root), "archive", source_commit, *REPLAY_TREES],
            capture_output=True,
            check=False,
        )
        if archive.returncode != 0:
            return (-1, "", f"git archive failed: {archive.stderr.decode('utf-8', 'replace')[:200]}")
        extract = subprocess.run(
            ["tar", "-x", "-C", str(root)], input=archive.stdout, capture_output=True, check=False
        )
        if extract.returncode != 0:
            return (-1, "", f"tar extract failed: {extract.stderr.decode('utf-8', 'replace')[:200]}")
        (root / "site").mkdir(exist_ok=True)
        env = dict(os.environ)
        env["MOR1_GENERATED_AT"] = clock
        env["PYTHONPATH"] = str(root)
        proc = subprocess.run(
            [interpreter, "-m", RENDER_MODULE],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        page = root / "site" / "reference.html"
        digest = _sha256_file(page) if page.is_file() else ""
        detail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return (proc.returncode, digest, detail)


def _verify_render_replay(
    *,
    repo_root: Path,
    source_commit: str,
    invocation: Any,
    expected_digest: Any,
) -> list[str]:
    if not isinstance(invocation, Mapping):
        return ["render replay skipped: render_invocation missing"]
    clock = invocation.get("generated_at")
    if not isinstance(clock, str) or not clock.strip():
        return [
            "render_invocation.generated_at missing — the presentation clock must be an "
            "explicit recorded build input, or no replay can confirm the committed page"
        ]
    env = invocation.get("env")
    if not isinstance(env, Mapping) or env.get("MOR1_GENERATED_AT") != clock:
        return [
            "render_invocation.env must record MOR1_GENERATED_AT equal to generated_at; "
            f"got {env!r}"
        ]
    argv = invocation.get("argv")
    interpreter = argv[0] if isinstance(argv, list) and argv else ""
    if not isinstance(interpreter, str) or not Path(interpreter).exists():
        # Replay needs a runnable interpreter; fall back to this process's.
        interpreter = sys.executable
    rc, digest, detail = _replay_render(repo_root, source_commit, interpreter, clock)
    if rc != 0:
        return [
            f"clean-checkout replay of {source_commit[:12]} exited {rc}: {detail}"
        ]
    if not digest:
        return [f"clean-checkout replay of {source_commit[:12]} produced no site/reference.html"]
    if digest != expected_digest:
        return [
            "clean-checkout replay does not reproduce the committed artifact: replayed "
            f"{digest[:16]}… != subject site/reference.html {str(expected_digest)[:16]}… "
            "(the committed page was not built from this subject with this clock)"
        ]
    return []


def _authenticate_binding(
    binding: Mapping[str, Any],
    *,
    repo_root: Path,
    tool_version: str | None,
    excluded: Any,
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

    # --- clean immutable subject -------------------------------------------
    # A packet captured from a dirty tree describes bytes that were never
    # committed. ``worktree_head_matches_source`` was tautological (head was
    # assigned FROM source_commit); this asks git instead.
    if binding.get("worktree_clean") is not True:
        errors.append(
            f"candidate_binding.worktree_clean is not exactly true: "
            f"{binding.get('worktree_clean')!r}"
        )
    tracked_status = binding.get("worktree_status_tracked")
    if not isinstance(tracked_status, list):
        errors.append("candidate_binding.worktree_status_tracked missing (clean-tree receipt)")
    elif tracked_status:
        errors.append(
            f"capture ran against a dirty worktree; tracked changes: {tracked_status!r}"
        )

    # --- every bound path is a SUBJECT-COMMIT blob, never current disk ------
    # Collected first and resolved in ONE ``cat-file --batch``: this clone
    # answers each individual git query in seconds.
    pending: list[tuple[str, Any, str]] = []

    def blob_check(rel: str, declared: Any, label: str) -> None:
        pending.append((rel, declared, label))

    def resolve_blob_checks() -> None:
        if not pending:
            return
        rels = tuple(dict.fromkeys(rel for rel, _, _ in pending))
        actual = dict(_git_blob_sha256_batch(repo_root, source_commit, rels))
        for rel, declared, label in pending:
            got = actual.get(rel)
            if got is None:
                errors.append(
                    f"{label}: {rel} does not exist in subject commit {source_commit[:12]}"
                )
            elif not isinstance(declared, str) or declared != got:
                errors.append(
                    f"{label}: {rel} declared {str(declared)[:16]}… != subject-commit blob "
                    f"{got[:16]}…"
                )
        pending.clear()

    blob_check("site/reference.html", binding.get("site_reference_sha256"), "site_reference_sha256")
    blob_check(
        "scripts/capture_page_evidence.py",
        binding.get("capture_tool_module_sha256"),
        "capture_tool_module_sha256",
    )
    blob_check(
        "scripts/market_reference_route_evidence.py",
        binding.get("verifier_module_sha256"),
        "verifier_module_sha256",
    )

    declared_tool_version = binding.get("capture_tool_version")
    if declared_tool_version != tool_version:
        errors.append(
            f"candidate_binding.capture_tool_version {declared_tool_version!r} "
            f"!= manifest tool.version {tool_version!r}"
        )

    # --- capture origin -----------------------------------------------------
    serve_root = binding.get("serve_root")
    if not isinstance(serve_root, str) or not re.fullmatch(
        r"http://127\.0\.0\.1:\d{1,5}", serve_root or ""
    ):
        errors.append(
            f"candidate_binding.serve_root {serve_root!r} is not an exact local loopback origin"
        )
    site_dir = binding.get("site_dir")
    canonical_site = str((repo_root / "site").resolve())
    if site_dir != canonical_site:
        errors.append(
            f"candidate_binding.site_dir {site_dir!r} != canonical repo site dir {canonical_site!r}"
        )

    if not isinstance(excluded, list) or excluded:
        errors.append(
            f"manifest.excluded must be exactly [] for a closed 32-cell world; got {excluded!r}"
        )

    invocation = binding.get("render_invocation")
    if not isinstance(invocation, Mapping):
        errors.append("candidate_binding.render_invocation missing")
    else:
        command = invocation.get("command")
        argv = invocation.get("argv")
        cwd = invocation.get("cwd")
        inputs = invocation.get("input_digests")
        outputs = invocation.get("output_digests")
        # FROZEN, not merely "mentions the builder". A substring test accepted
        # command="echo build_market_reference but do nothing" with
        # argv=["/bin/false"]: the string named the builder and the list was
        # non-empty, so a render that never ran validated clean.
        if command != RENDER_COMMAND:
            errors.append(
                f"render_invocation.command {command!r} != frozen {RENDER_COMMAND!r}"
            )
        if not isinstance(argv, list) or len(argv) != 3:
            errors.append(
                f"render_invocation.argv must be exactly [<python>, '-m', "
                f"'{RENDER_MODULE}']; got {argv!r}"
            )
        else:
            interpreter = str(argv[0] or "")
            if not _PYTHON_EXE_RE.fullmatch(Path(interpreter).name):
                errors.append(
                    f"render_invocation.argv[0] {interpreter!r} is not a python interpreter"
                )
            if list(argv[1:]) != ["-m", RENDER_MODULE]:
                errors.append(
                    f"render_invocation.argv[1:] {list(argv[1:])!r} != ['-m', '{RENDER_MODULE}']"
                )
        if cwd != str(repo_root.resolve()):
            errors.append(
                f"render_invocation.cwd {cwd!r} != repo root {str(repo_root.resolve())!r}"
            )
        if invocation.get("returncode") != 0:
            errors.append(
                f"render_invocation.returncode {invocation.get('returncode')!r} is not 0"
            )
        if not isinstance(inputs, Mapping):
            errors.append("render_invocation.input_digests missing")
        else:
            for rel in REQUIRED_RENDER_INPUTS:
                blob_check(rel, inputs.get(rel), "render_invocation.input_digests")
        if not isinstance(outputs, Mapping) or not outputs.get("site/reference.html"):
            errors.append("render_invocation.output_digests missing site/reference.html")
        elif outputs.get("site/reference.html") != binding.get("site_reference_sha256"):
            errors.append(
                "render_invocation.output_digests[site/reference.html] != site_reference_sha256"
            )

    # --- local asset graph derived from the rendered page -------------------
    assets = binding.get("local_asset_digests")
    if not isinstance(assets, Mapping) or not assets:
        errors.append("candidate_binding.local_asset_digests missing")
    else:
        html_bytes = _git_blob(repo_root, source_commit, "site/reference.html")
        if html_bytes is None:
            errors.append("cannot derive local assets: site/reference.html absent from subject")
        else:
            derived = derive_local_assets(html_bytes.decode("utf-8", "replace"))
            declared_keys = sorted(str(k) for k in assets)
            missing_assets = [rel for rel in derived if rel not in assets]
            extra_assets = [rel for rel in declared_keys if rel not in derived]
            if missing_assets:
                errors.append(
                    f"local_asset_digests omits assets the rendered page loads: {missing_assets}"
                )
            if extra_assets:
                errors.append(
                    f"local_asset_digests declares assets the page does not load: {extra_assets}"
                )
            # Floor: the historically hard-coded set must still be covered, so a
            # derivation that silently stopped finding assets is caught too.
            below_floor = [rel for rel in REQUIRED_SHARED_ASSETS if rel not in derived]
            if below_floor:
                errors.append(
                    f"derived local asset set lost known dependencies {below_floor}; "
                    "the derivation, not the page, is the suspect"
                )
        for rel, digest in sorted(assets.items()):
            if not isinstance(rel, str) or not isinstance(digest, str):
                errors.append(f"local_asset_digests has a non-string entry {rel!r}")
                continue
            blob_check(rel, digest, "local_asset_digests")

    resolve_blob_checks()

    # --- deterministic clean-checkout replay --------------------------------
    # A command/argv receipt can be perfectly self-consistent while the
    # committed page was produced from a dirty tree or a different clock. The
    # only proof is to REBUILD from the subject commit in a fresh checkout and
    # compare bytes.
    if not errors:
        errors.extend(
            _verify_render_replay(
                repo_root=repo_root,
                source_commit=source_commit,
                invocation=binding.get("render_invocation"),
                expected_digest=binding.get("site_reference_sha256"),
            )
        )

    # --- evidence descendant purity ----------------------------------------
    rc_diff, changed = _git(
        repo_root, "diff", "--name-only", source_commit, "HEAD", "--", *OWNED_SOURCE_PATHS
    )
    if rc_diff != 0:
        errors.append("unable to diff subject commit against HEAD for evidence-descendant purity")
    elif changed.strip():
        errors.append(
            "evidence descendant changed owned non-evidence path(s) after the subject "
            f"commit: {sorted(changed.split())}"
        )
    rc_merges, merge_count = _git(
        repo_root, "rev-list", "--count", "--merges", f"{source_commit}..HEAD"
    )
    if rc_merges == 0 and merge_count.strip() == "0":
        # Linear branch history: the strong form also holds — every path that
        # moved after the subject must live under the evidence directory.
        rc_all, all_changed = _git(repo_root, "diff", "--name-only", source_commit, "HEAD")
        if rc_all == 0 and all_changed.strip():
            stray = sorted(
                p for p in all_changed.split() if not p.startswith(EVIDENCE_DIR_REL + "/")
            )
            if stray:
                errors.append(
                    f"evidence descendant changed non-evidence path(s): {stray}"
                )
    return errors


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------


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

    excluded = manifest.get("excluded")
    binding = manifest.get("candidate_binding")
    if not isinstance(binding, Mapping):
        errors.append("missing candidate_binding (subject/tree/site/serve/capture identity)")
        binding = {}
    else:
        for key in sorted(REQUIRED_BINDING_KEYS):
            val = binding.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"candidate_binding.{key} missing or empty")
        errors.extend(
            _authenticate_binding(
                binding,
                repo_root=root,
                tool_version=version_raw if isinstance(version_raw, str) else None,
                excluded=excluded,
            )
        )

    serve_root_origin = (
        _origin_of(binding.get("serve_root")) if isinstance(binding, Mapping) else None
    )

    # Order comes from the SUBJECT-COMMIT rendered page, not from disk and not
    # from registry order (which the builder regroups).
    dom_order: list[str] | None = None
    subject_commit = binding.get("source_commit") if isinstance(binding, Mapping) else None
    if isinstance(subject_commit, str) and GIT_SHA_RE.fullmatch(subject_commit):
        subject_html = _git_blob(root, subject_commit, "site/reference.html")
        if subject_html is not None:
            dom_order = rendered_entry_order(subject_html.decode("utf-8", "replace"))
    probes = resolve_probe_queries(root, dom_order=dom_order)
    errors.extend(_probe_sanity(probes))
    case_ids_map = {
        case["expect"].get("query_q"): expected_query_entry_ids(
            case["expect"].get("query_q"), repo_root=root, dom_order=dom_order
        )
        for case in ROUTE_CASES
    }
    probes = dict(probes)
    probes["_case_ids"] = {k: v for k, v in case_ids_map.items() if k is not None}
    full_library_ids = list(probes["full_ids"])
    full_total = len(full_library_ids)

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
    # One declared file AND digest owner per logical 32-cell identity. The old
    # rule only rejected reuse across routes, so one PNG could stand for
    # dark/light, en/zh, or desktop/mobile inside a single route.
    digest_owners: dict[str, list[tuple[Any, ...]]] = {}
    file_owners: dict[str, list[tuple[Any, ...]]] = {}
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

        if "route_journeys" in page:
            errors.append(
                f"page {page_id!r}: legacy plural route_journeys is retired; a journey "
                "must be one axes-bound route_journey receipt"
            )
        journey = page.get("route_journey")
        if case["expect"].get("require_journeys"):
            if not isinstance(journey, Mapping):
                errors.append(f"page {page_id!r}: missing route_journey")
            else:
                errors.extend(
                    f"page {page_id!r}: {err}"
                    for err in _validate_journey(
                        case, journey, probes=probes, origin=serve_root_origin
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
            # Closed world. A forced or authenticated cell used to be skipped
            # silently by the REST-key helper, so an extra forced cell or a
            # substituted access cell rode along invisibly.
            force_state = state.get("force_state")
            if force_state is not None:
                errors.append(
                    f"page {page_id!r}: state carries force_state {force_state!r}; the frozen "
                    "world is anonymous / no-force only"
                )
                continue
            access = state.get("access")
            if access != REQUIRED_ACCESS:
                errors.append(
                    f"page {page_id!r}: state access {access!r} != required {REQUIRED_ACCESS!r}"
                )
                continue
            viewport = state.get("viewport")
            locale = state.get("locale")
            theme = state.get("theme")
            if not all(isinstance(x, str) for x in (viewport, locale, theme)):
                errors.append(
                    f"page {page_id!r}: state missing viewport/locale/theme identity: {state!r}"
                )
                continue
            key = (viewport, locale, theme)
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
            logical = (page_id, viewport, locale, theme)
            logical_keys.append(logical)
            if not state.get("captured"):
                errors.append(f"page {page_id!r} cell {key}: not captured")
                continue
            present.add(key)

            for bag_name in ("console_errors", "failed_responses"):
                bag = state.get(bag_name)
                if not isinstance(bag, list):
                    errors.append(
                        f"page {page_id!r} cell {key}: missing per-cell {bag_name}; a page-level "
                        "aggregate cannot prove this cell was clean"
                    )
                elif bag:
                    errors.append(f"page {page_id!r} cell {key}: {bag_name} not empty: {bag!r}")

            sha = state.get("sha256")
            if isinstance(sha, str) and sha:
                digest_owners.setdefault(sha, []).append(logical)
            file_name = state.get("file")
            if isinstance(file_name, str) and file_name:
                manifest_files.add(Path(file_name).name)
                file_owners.setdefault(Path(file_name).name, []).append(logical)
            route_errs = _validate_route_state(
                case,
                state,
                probes=probes,
                full_library_ids=full_library_ids,
                full_total=full_total,
                origin=serve_root_origin,
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

    for sha, owners in sorted(digest_owners.items()):
        if len(owners) > 1:
            errors.append(
                f"screenshot digest {sha[:16]}… is claimed by {len(owners)} distinct logical "
                f"cells {sorted(owners)}; each 32-cell identity owns exactly one image"
            )
    for name, owners in sorted(file_owners.items()):
        if len(owners) > 1:
            errors.append(
                f"screenshot file {name!r} is claimed by {len(owners)} distinct logical "
                f"cells {sorted(owners)}"
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
    probes: Mapping[str, Any],
    full_library_ids: Sequence[str],
    full_total: int,
    origin: str | None,
) -> list[str]:
    expect = case["expect"]
    rs = state.get("route_state")
    if not isinstance(rs, Mapping):
        return ["missing route_state (capture must record final URL / DOM route probe)"]
    errors: list[str] = []
    missing_keys = sorted(REQUIRED_ROUTE_STATE_KEYS - set(rs))
    if missing_keys:
        errors.append(f"route_state missing keys {missing_keys}")
    if "journeys" in rs:
        errors.append(
            "route_state.journeys is retired: one default-context journey copied into "
            "every cell claims behavior the cell never executed"
        )

    route = str(case["route"])
    want_path, want_q, want_hash = parse_route(route)

    got_hash = rs.get("hash")
    if got_hash != want_hash:
        errors.append(f"hash {got_hash!r} != expected {want_hash!r}")
    got_q = rs.get("query_q")
    if want_q is None:
        if got_q not in (None, ""):
            errors.append(f"query_q {got_q!r} expected absent")
    elif got_q != want_q:
        errors.append(f"query_q {got_q!r} != expected {want_q!r}")
    if str(rs.get("pathname") or "") != want_path:
        errors.append(f"pathname {rs.get('pathname')!r} != expected {want_path!r}")
    if want_q is not None and rs.get("rf_q_value") not in (want_q, str(want_q)):
        errors.append(f"rf_q_value {rs.get('rf_q_value')!r} != expected {want_q!r}")
    if want_q is None and rs.get("rf_q_value") not in (None, ""):
        errors.append(f"rf_q_value {rs.get('rf_q_value')!r} expected empty")
    if bool(rs.get("miss_visible")) != bool(expect.get("miss_visible")):
        errors.append(
            f"miss_visible {rs.get('miss_visible')!r} != expected {expect.get('miss_visible')!r}"
        )
    # Issue 6782: the recovery panel must echo the exact unknown anchor back to
    # the reader. `miss_visible` alone is not a receipt — a panel that appears
    # while naming the wrong entry, or nothing at all, satisfies it.
    got_slug = rs.get("miss_q_text")
    if expect.get("miss_visible"):
        want_slug = want_hash.lstrip("#")
        if got_slug != want_slug:
            errors.append(
                f"miss_q_text {got_slug!r} != the unknown anchor {want_slug!r} "
                "(the recovery panel must name the entry the reader asked for)"
            )
    elif got_slug not in (None, ""):
        errors.append(
            f"miss_q_text {got_slug!r} is populated on a route with no miss state"
        )
    want_sel = expect.get("selected_id")
    got_sel = rs.get("selected_id")
    if want_sel is None:
        if got_sel not in (None, ""):
            errors.append(f"selected_id {got_sel!r} expected null")
    elif got_sel != want_sel:
        errors.append(f"selected_id {got_sel!r} != expected {want_sel!r}")

    expected_ids: Sequence[str]
    if expect.get("require_membership"):
        expected_ids = expected_query_entry_ids_cached(want_q, probes)
    else:
        expected_ids = list(full_library_ids)
    errors.extend(
        _exact_membership(
            rs,
            expected_ids,
            label="route_state",
            full_total=full_total,
            require_count_label=bool(expect.get("require_count_label")),
        )
    )

    min_results = expect.get("min_visible_results")
    count = rs.get("visible_result_count")
    if isinstance(min_results, int):
        if not isinstance(count, int) or count < min_results:
            errors.append(
                f"visible_result_count {count!r} < required minimum {min_results}"
            )

    if expect.get("require_count_label"):
        if not rs.get("count_label_visible"):
            errors.append("count_label_visible is false")
        label = rs.get("count_label_text")
        if not isinstance(label, str) or not label.strip():
            errors.append("count_label_text missing")

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

    # Closed URL identity on BOTH recorded URLs plus the parsed fields beside
    # them. requested_url used to be recorded and never checked, so a forged one
    # rode along; final_url was substring-matched, so a cross-origin URL, an
    # extra query key, a duplicated `q`, or a blank `?q=` all passed.
    errors.extend(
        _validate_url(
            rs.get("requested_url"),
            label="requested_url",
            expect_path=want_path,
            expect_q=want_q,
            expect_hash=want_hash,
            origin=origin,
        )
    )
    errors.extend(
        _validate_recorded_url(
            rs,
            label="route_state",
            expect_path=want_path,
            expect_q=want_q,
            expect_hash=want_hash,
            origin=origin,
            href_key="final_url",
        )
    )
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
