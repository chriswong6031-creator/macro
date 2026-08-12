#!/usr/bin/env python3
"""Bounded browser evidence capture + UX-smell census for registry-listed pages.

What this is
------------
An *evidence* tool, not a judge and not a crawler. It walks a fixed list of routes
taken from the product page registry (``data/product_experience/page_registry.json``,
schema ``mastermind.page_registry.v1``), loads each one anonymously in a real
browser, screenshots a declared state matrix, and records a set of literally
measurable page facts. It scores nothing, ranks nothing, and labels no page good
or bad — a heuristic here identifies a review target for a human, and that is the
whole of its authority.

Contract
--------
1. **Anonymous only.** No credential is ever entered, synthesized, or read. Free /
   Essential / Pro states are recorded as explicit *gaps* with a reason, never as a
   capture. Because the run is anonymous, no premium payload can enter the
   artifacts by construction.
2. **A state that could not be captured is recorded, never omitted and never
   faked.** Loading/empty/stale/error page states are gaps with a reason; a page
   that 404s or times out is ``captured: false`` with the error text.
3. **No browser is never a pass.** ``playwright`` is imported lazily inside
   ``playwright_page_driver``; a missing library or chromium binary raises
   ``CaptureUnavailable`` and the CLI exits nonzero with outcome
   ``verifier_unavailable``, writing no artifact over the committed evidence.
4. **The driver is an injected seam** (``PageDriver``). Tests supply an in-memory
   fake; production supplies playwright. Nothing in the test path imports a browser.
5. **Off the render path.** Never wired into CI or the nightly — a render-budget
   law repo does not spend 4 cores on screenshots. Run it locally.
6. **Screenshots are content-addressed and local.** ``evidence/<sha256[:16]>.png``
   is gitignored; only the manifest + smell report (which carry the digests) are
   committed.
7. **A console error names the asset it came from.** Each entry is
   ``{"text": ..., "source_url": ...}`` and every response the page took a 4xx/5xx
   on is listed separately in ``failed_responses``. The 2026-08 census recorded a
   bare ``"401"`` on 12 of 13 P0 pages and could not say which request produced
   it — an unattributable error is a dead end for the human who has to fix it.
8. **No subprocess, no directory enumeration, anywhere in this module.** Both are
   statically opaque edges, and ``scripts/ci_scope_dependencies.py`` widens a
   module carrying one to every ``data/**`` path it mentions — which re-reds the
   ci_pack narrow-diff contract through the ``product-experience-capture`` job.
   ``_git_head_sha`` therefore reads ``.git`` by hand and the self-check tracks
   the files it wrote instead of globbing for them.

Locale/theme are applied the way the site's own toggle applies them
(``templates/theme.js``): ``setTheme`` sets ``data-theme`` on ``<html>`` and
persists ``localStorage.theme`` while clearing ``themeAuto``; ``setLang`` sets
``data-lang``, syncs ``documentElement.lang``, and persists ``localStorage.lang``.
Both are seeded pre-navigation *and* re-applied post-load through the page's own
``window.setTheme`` / ``window.setLang`` when present, and the state actually
observed on ``<html>`` is written back into the manifest.

Usage::

    python3 scripts/capture_page_evidence.py --self-check
    python3 scripts/capture_page_evidence.py --site-dir site --priority P0 --repo macro
    python3 scripts/capture_page_evidence.py --base-url https://www.mastermind-x.com \\
        --routes /index.html --viewports desktop --themes light,dark --max-pages 1
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
import socketserver
import struct
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

MODULE_REF = "scripts/capture_page_evidence.py"
# 1.1.0: attributed console errors, failed_responses, honest --routes selection.
# This is stamped into every artifact as provenance, so it moves whenever the
# emitted shape does — two byte-different manifests must never claim one version.
TOOL_VERSION = "1.1.0"

# v2: a console error carries the asset it came from, and a page carries the
# responses that failed. v1 recorded bare error strings, which the census could
# not attribute to anything.
MANIFEST_SCHEMA = "mastermind.p0_evidence.v2"
SMELL_SCHEMA = "mastermind.ux_smell_report.v1"
REGISTRY_SCHEMA = "mastermind.page_registry.v1"

DEFAULT_REGISTRY = "data/product_experience/page_registry.json"
DEFAULT_OUTPUT_DIR = "data/product_experience/evidence"
DEFAULT_MANIFEST = "data/product_experience/p0_evidence_manifest.json"
DEFAULT_SMELLS = "data/product_experience/ux_smell_report.json"

# A census identifies itself. This is not a crawler: it follows no link, obeys a
# hard page cap, sleeps between loads, and only ever requests registry routes.
USER_AGENT = "mastermind-page-census/1.0 (internal product observability)"

VIEWPORTS: Mapping[str, tuple[int, int]] = {
    "desktop": (1440, 900),
    "tablet": (820, 1180),
    "mobile": (390, 844),
}
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "zh")
SUPPORTED_THEMES: tuple[str, ...] = ("light", "dark")

ACCESS_ANONYMOUS = "anonymous"
GATED_ACCESS_STATES: tuple[str, ...] = ("free", "essential", "pro")
GATED_ACCESS_REASON = "requires authenticated session; not automatable without approved fixtures"
SYNTHETIC_PAGE_STATES: tuple[str, ...] = ("loading", "empty", "stale", "error")
SYNTHETIC_PAGE_STATE_REASON = "state not synthesizable against static output"

# A family row stands for many concrete URLs (per-ticker analyzers, per-slug
# dossiers). Capturing "the family" is meaningless, so a family is skipped unless
# the registry row names one concrete exemplar to stand in for it.
FAMILY_ROUTE_KINDS = frozenset({"family", "template", "pattern", "dynamic", "parameterized"})
EXEMPLAR_FIELDS: tuple[str, ...] = ("exemplar_route", "exemplar_url", "exemplar")
_ROUTE_PLACEHOLDERS: tuple[str, ...] = ("{", "<", "*", "/:")

# --routes replaces registry selection wholesale, so the parser's --priority /
# --repo defaults describe a filter that never ran. Recording them anyway is how a
# terminal manifest came to claim repo "macro" while capturing app.mastermind-x.com.
ROUTES_SELECTION_NOTE = (
    "--routes overrode registry selection; the --priority and --repo filters were not applied"
)

OUTCOME_CAPTURED = "captured"
OUTCOME_PARTIAL = "partial"
OUTCOME_UNAVAILABLE = "verifier_unavailable"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PARTIAL = 3
EXIT_UNAVAILABLE = 4

INSTALL_HINT = (
    "python3 -m pip install playwright && python3 -m playwright install chromium"
)

# Every probe below is APPROXIMATE and says so in the report. They exist to point a
# human at a page, never to decide anything about it.
DEFAULT_OBSERVER_CONFIG: Mapping[str, Any] = {
    # Class-name heuristics: this estate has no single panel component, so a
    # "panel" is whatever looks like one. Over- and under-counts are expected.
    "panel_selectors": [".card", ".panel", "[class*='card']"],
    "long_paragraph_words": 120,
    "asof_probe": {
        "selectors": ["[data-asof]", ".asof", ".freshness"],
        "text_patterns": ["as of", "数据截至"],
    },
    "source_probe": {
        "selectors": ["[data-source]", ".source", ".provenance", "[data-src]"],
        "text_patterns": ["source:", "来源", "数据来源"],
    },
    # Distinct-match lists are capped so a committed artifact stays bounded.
    "max_hit_samples": 25,
}

METRIC_KEYS: tuple[str, ...] = (
    "document_height_px",
    "section_count",
    "heading_counts",
    "duplicate_heading_texts",
    "panel_count",
    "visible_word_count",
    "long_paragraph_count",
    "raw_slug_hits",
    "raw_slug_hit_count",
    "todo_placeholder_hits",
    "todo_placeholder_hit_count",
    "horizontal_overflow",
    "elements_wider_than_viewport",
    "console_error_count",
    "request_count",
    "payload_bytes_total",
    "asof_present",
    "source_present",
    "screenshot_completion",
)

METRIC_NOTES: Mapping[str, str] = {
    "section_count": "direct <section> children of <body> plus direct element children of <main>; an approximation of 'how many blocks is this page'",
    "panel_count": "class-name heuristic over the configured selector list; both over- and under-counts are expected",
    "visible_word_count": "whitespace-split innerText of <body>; Chinese text is not word-segmented, so a zh capture undercounts relative to en",
    "raw_slug_hits": "visible text matching 3+ segment snake_case; legitimate identifiers (file names, API keys quoted on purpose) match too",
    "duplicate_heading_texts": "case-folded visible heading text seen more than once; a repeated section label across tabs is a legitimate duplicate",
    "asof_present": "approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict",
    "source_present": "approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict",
    "payload_bytes_total": "sum of response body sizes reported by the driver for the reference state; excludes bodies the driver could not size",
    "console_error_count": "distinct console 'error' texts across every captured state of the page",
    "screenshot_completion": "captured states / attempted states for this page; states the registry excludes are not attempted and are recorded as gaps",
}

MD_DISCLAIMER = (
    "Heuristics identify review targets; they do not determine that a page is bad."
)


class CaptureUnavailable(RuntimeError):
    """No real browser is reachable. Never downgraded to a successful capture."""


class RegistryError(RuntimeError):
    """The page registry is missing or unreadable. Reported cleanly, never traced."""


@dataclass(frozen=True)
class CaptureCell:
    """One capture cell: a page plus the exact state to put it in."""

    page_id: str
    route: str
    viewport: str
    width: int
    height: int
    locale: str
    theme: str
    access: str = ACCESS_ANONYMOUS

    @property
    def cell_id(self) -> str:
        return f"{self.page_id}|{self.viewport}|{self.locale}|{self.theme}|{self.access}"


@dataclass(frozen=True)
class CellObservation:
    """Exactly what the driver saw in one cell. Nothing here is a judgement."""

    cell_id: str
    loaded: bool
    error: str | None = None
    screenshot_png: bytes = b""
    observed: Mapping[str, Any] = field(default_factory=dict)
    # ``{"text": str, "source_url": str | None}`` — an error nobody can attribute
    # to an asset is a dead end, so the source URL travels with the text and is
    # null only when the driver genuinely had none (a pageerror has no location).
    console_errors: tuple[Mapping[str, Any], ...] = ()
    # ``{"url": str, "status": int}`` for every response the page took a 4xx/5xx
    # on. This is what turns a bare "401" console line into a named request.
    failed_responses: tuple[Mapping[str, Any], ...] = ()
    request_count: int = 0
    payload_bytes_total: int = 0
    applied_theme: str | None = None
    applied_locale: str | None = None


class PageDriver(Protocol):
    """The injected observer seam. Tests supply a fake; production supplies playwright."""

    def capture(
        self, *, url: str, cell: CaptureCell, timeout_s: float
    ) -> CellObservation:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Serialize deterministically so two runs with the same --as-of are byte-equal."""

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def module_source_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _png_dimensions(png: bytes) -> tuple[int, int] | None:
    """Read width/height out of the PNG IHDR — no image library, no dependency."""

    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", png[16:24])
    return int(width), int(height)


def _is_hex_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value.lower())


def _read_text(path: Path) -> str | None:
    """One known path, read or not. No enumeration, no subprocess — see docstring §8."""

    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None


def _git_head_sha(start: Path) -> str | None:
    """Resolve the checkout's HEAD by reading ``.git`` by hand. Best-effort, never guessed.

    ``git rev-parse`` used to do this, but a subprocess is an opaque edge to the CI
    scope analyzer and widens this module's suite to every ``data/**`` path it names.
    The walk is upward because ``--site-dir`` is usually a subdirectory of the
    checkout. Anything unexpected — no ``.git``, a symbolic ref that resolves
    nowhere, content that is not a sha — returns None: this field is provenance,
    and a wrong sha is worse than an honest null.
    """

    gitdir: Path | None = None
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            gitdir = marker
            break
        if marker.is_file():  # linked worktree: ".git" is a pointer file
            pointer = _read_text(marker)
            if not pointer or not pointer.startswith("gitdir:"):
                return None
            target = Path(pointer.split(":", 1)[1].strip())
            gitdir = target if target.is_absolute() else marker.parent / target
            break
    if gitdir is None:
        return None

    head = _read_text(gitdir / "HEAD")
    if head is None:
        return None
    if _is_hex_sha(head):
        return head  # detached HEAD
    if not head.startswith("ref:"):
        return None
    ref = head.split(":", 1)[1].strip()

    # A linked worktree keeps its own HEAD but shares refs with the common dir.
    common = gitdir
    pointer = _read_text(gitdir / "commondir")
    if pointer:
        target = Path(pointer)
        common = target if target.is_absolute() else gitdir / target

    for base in (gitdir, common):
        loose = _read_text(base / ref)
        if loose is not None:
            return loose if _is_hex_sha(loose) else None

    packed = _read_text(common / "packed-refs")
    for line in (packed or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "^")):  # comment / peeled tag
            continue
        sha, _, name = line.partition(" ")
        if name.strip() == ref and _is_hex_sha(sha):
            return sha
    return None


# ---------------------------------------------------------------------------
# registry selection
# ---------------------------------------------------------------------------


def load_registry(path: Path | str) -> list[dict[str, Any]]:
    """Read the registry another builder owns. Tolerant of its container shape."""

    registry_path = Path(path)
    if not registry_path.exists():
        raise RegistryError(
            f"page registry not found: {registry_path} "
            "(build it with scripts/build_product_page_registry.py, or pass --routes to "
            "capture an explicit list without a registry)"
        )
    try:
        document = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RegistryError(f"page registry is not readable JSON: {registry_path}: {exc}") from exc

    if isinstance(document, list):
        rows: Any = document
    elif isinstance(document, dict):
        schema = document.get("schema")
        if schema and schema != REGISTRY_SCHEMA:
            print(
                f"::warning title=capture-page-evidence::registry schema is {schema!r}, "
                f"expected {REGISTRY_SCHEMA!r}; reading it anyway",
                flush=True,
            )
        rows = document.get("pages") or document.get("rows") or document.get("entries") or []
    else:
        raise RegistryError(f"page registry root must be an object or a list: {registry_path}")

    if not isinstance(rows, list):
        raise RegistryError(f"page registry rows must be a list: {registry_path}")
    return [row for row in rows if isinstance(row, dict)]


def _row_list_field(row: Mapping[str, Any], key: str, allowed: Sequence[str]) -> tuple[str, ...] | None:
    """Read a declared axis (themes/locales). ``None`` means the registry is silent.

    The registry writes the sentinel ``"unknown"`` for an axis it could not resolve,
    so an unresolvable declaration must read as SILENT, never as "supports nothing" —
    the latter would expand to zero cells and hand back a page with no evidence at
    all. Silence attempts every requested axis and records what the page settled on.
    """

    raw = row.get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, (list, tuple)):
        return None
    values = tuple(v for v in (str(item).strip().lower() for item in raw) if v in allowed)
    return values or None


def exemplar_route(row: Mapping[str, Any]) -> str | None:
    for key in EXEMPLAR_FIELDS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def is_family_row(row: Mapping[str, Any]) -> bool:
    kind = str(row.get("route_kind") or "").strip().lower()
    if kind in FAMILY_ROUTE_KINDS:
        return True
    route = str(row.get("route") or "")
    return any(token in route for token in _ROUTE_PLACEHOLDERS)


def normalize_row(row: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    route = str(row.get("route") or "").strip()
    page_id = str(row.get("page_id") or "").strip() or (route or f"row_{index}")
    family = is_family_row(row)
    exemplar = exemplar_route(row)
    return {
        "page_id": page_id,
        "route": route,
        "capture_route": exemplar if (family and exemplar) else route,
        "repo": str(row.get("repo") or "").strip().lower(),
        "priority": str(row.get("priority") or "").strip().upper(),
        "route_kind": str(row.get("route_kind") or "").strip().lower(),
        "is_family": family,
        "exemplar": exemplar,
        "themes": _row_list_field(row, "themes", SUPPORTED_THEMES),
        "locales": _row_list_field(row, "locales", SUPPORTED_LOCALES),
    }


def select_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    priority: str | None,
    repo: str | None,
    max_pages: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Pick the rows to capture. Returns (selected, excluded-with-reason)."""

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    want_priority = (priority or "").strip().upper()
    want_repo = (repo or "").strip().lower()

    for index, raw in enumerate(rows):
        row = normalize_row(raw, index=index)
        if want_priority and row["priority"] and row["priority"] != want_priority:
            continue
        if want_repo and row["repo"] and row["repo"] != want_repo:
            continue
        if not row["capture_route"]:
            excluded.append({"page_id": row["page_id"], "reason": "row carries no route"})
            continue
        if row["is_family"] and not row["exemplar"]:
            excluded.append(
                {
                    "page_id": row["page_id"],
                    "reason": "route family with no exemplar route; a family stands for many URLs and is not itself capturable",
                }
            )
            continue
        selected.append(row)

    selected.sort(key=lambda row: (row["capture_route"], row["page_id"]))
    if max_pages > 0 and len(selected) > max_pages:
        for row in selected[max_pages:]:
            excluded.append(
                {"page_id": row["page_id"], "reason": f"beyond the --max-pages cap of {max_pages}"}
            )
        selected = selected[:max_pages]
    return selected, excluded


def synthesize_rows(routes: Sequence[str], registry_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """--routes override: reuse a matching registry row, else synthesize a minimal one.

    Synthesized rows declare no themes/locales, so the requested axes are all
    attempted — the registry is what narrows a page to (say) dark-only.
    """

    by_route: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(registry_rows):
        row = normalize_row(raw, index=index)
        for key in {row["route"], row["capture_route"]}:
            if key:
                by_route.setdefault(key, row)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for route in routes:
        route = route.strip()
        if not route or route in seen:
            continue
        seen.add(route)
        match = by_route.get(route)
        if match is not None:
            out.append(dict(match))
            continue
        page_id = route.strip("/").replace("/", "_") or "root"
        out.append(
            {
                "page_id": page_id,
                "route": route,
                "capture_route": route,
                "repo": "",
                "priority": "",
                "route_kind": "explicit_override",
                "is_family": False,
                "exemplar": None,
                "themes": None,
                "locales": None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# state matrix
# ---------------------------------------------------------------------------


def state_matrix(
    row: Mapping[str, Any],
    *,
    viewports: Sequence[str],
    locales: Sequence[str],
    themes: Sequence[str],
) -> tuple[list[CaptureCell], list[dict[str, Any]]]:
    """Expand one row into cells, and record the axes the registry excludes as gaps."""

    gaps: list[dict[str, Any]] = []

    declared_locales = row.get("locales")
    declared_themes = row.get("themes")

    use_locales = [loc for loc in locales if declared_locales is None or loc in declared_locales]
    use_themes = [theme for theme in themes if declared_themes is None or theme in declared_themes]

    for locale in locales:
        if locale not in use_locales:
            gaps.append(
                {
                    "dimension": "locale",
                    "value": locale,
                    "captured": False,
                    "reason": f"registry declares locales {sorted(declared_locales or ())} for this page",
                }
            )
    for theme in themes:
        if theme not in use_themes:
            gaps.append(
                {
                    "dimension": "theme",
                    "value": theme,
                    "captured": False,
                    "reason": f"registry declares themes {sorted(declared_themes or ())} for this page",
                }
            )

    cells: list[CaptureCell] = []
    for viewport in viewports:
        width, height = VIEWPORTS[viewport]
        for locale in use_locales:
            for theme in use_themes:
                cells.append(
                    CaptureCell(
                        page_id=str(row["page_id"]),
                        route=str(row["capture_route"]),
                        viewport=viewport,
                        width=width,
                        height=height,
                        locale=locale,
                        theme=theme,
                    )
                )
    return cells, gaps


def access_and_page_state_gaps() -> list[dict[str, Any]]:
    """The states this tool refuses to fake. Recorded on every page, always."""

    gaps: list[dict[str, Any]] = [
        {"dimension": "access", "value": state, "captured": False, "reason": GATED_ACCESS_REASON}
        for state in GATED_ACCESS_STATES
    ]
    gaps.extend(
        {
            "dimension": "page_state",
            "value": state,
            "captured": False,
            "reason": SYNTHETIC_PAGE_STATE_REASON,
        }
        for state in SYNTHETIC_PAGE_STATES
    )
    return gaps


# ---------------------------------------------------------------------------
# metrics assembly
# ---------------------------------------------------------------------------


def _null_metrics() -> dict[str, Any]:
    """Every metric key present, all null. A page with no capture still has a shape."""

    metrics: dict[str, Any] = {key: None for key in METRIC_KEYS}
    metrics["screenshot_completion"] = 0.0
    metrics["measured_in"] = None
    metrics["by_viewport"] = {}
    return metrics


def _metrics_from(observed: Mapping[str, Any]) -> dict[str, Any]:
    hits = list(observed.get("raw_slug_hits") or ())
    todos = list(observed.get("todo_placeholder_hits") or ())
    return {
        "document_height_px": observed.get("document_height_px"),
        "section_count": observed.get("section_count"),
        "heading_counts": dict(observed.get("heading_counts") or {}),
        "duplicate_heading_texts": list(observed.get("duplicate_heading_texts") or ()),
        "panel_count": observed.get("panel_count"),
        "visible_word_count": observed.get("visible_word_count"),
        "long_paragraph_count": observed.get("long_paragraph_count"),
        "raw_slug_hits": hits,
        "raw_slug_hit_count": observed.get("raw_slug_hit_count", len(hits)),
        "todo_placeholder_hits": todos,
        "todo_placeholder_hit_count": observed.get("todo_placeholder_hit_count", len(todos)),
        "horizontal_overflow": observed.get("horizontal_overflow"),
        "elements_wider_than_viewport": observed.get("elements_wider_than_viewport"),
        "asof_present": observed.get("asof_present"),
        "source_present": observed.get("source_present"),
    }


def _page_metrics(
    captured: Sequence[tuple[CaptureCell, CellObservation]],
    *,
    attempted: int,
    console_errors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics = _null_metrics()
    metrics["screenshot_completion"] = round(len(captured) / attempted, 4) if attempted else 0.0
    # The metric note says "distinct console 'error' TEXTS", and it keeps that
    # meaning under attribution: one message emitted by two assets is one text.
    metrics["console_error_count"] = len({str(entry.get("text") or "") for entry in console_errors})
    if not captured:
        return metrics

    # The reference state is the first captured cell in matrix order: one page load
    # is one measurement, so a single blob is reported rather than a blend of six.
    ref_cell, ref_obs = captured[0]
    metrics.update(_metrics_from(ref_obs.observed))
    metrics["request_count"] = ref_obs.request_count
    metrics["payload_bytes_total"] = ref_obs.payload_bytes_total
    metrics["measured_in"] = {
        "viewport": ref_cell.viewport,
        "locale": ref_cell.locale,
        "theme": ref_cell.theme,
        "access": ref_cell.access,
    }

    by_viewport: dict[str, Any] = {}
    for cell, observation in captured:
        if cell.viewport in by_viewport:
            continue
        by_viewport[cell.viewport] = {
            "document_height_px": observation.observed.get("document_height_px"),
            "horizontal_overflow": observation.observed.get("horizontal_overflow"),
            "elements_wider_than_viewport": observation.observed.get("elements_wider_than_viewport"),
        }
    metrics["by_viewport"] = by_viewport
    return metrics


# ---------------------------------------------------------------------------
# capture run
# ---------------------------------------------------------------------------


def write_screenshot(png: bytes, output_dir: Path) -> tuple[Path, str]:
    """Content-address the bytes. Identical states across pages share one file."""

    digest = hashlib.sha256(png).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{digest[:16]}.png"
    if not path.exists():
        path.write_bytes(png)
    return path, digest


def page_url(base: str, route: str) -> str:
    if route.startswith(("http://", "https://")):
        return route
    return base.rstrip("/") + "/" + route.lstrip("/")


def run_capture(
    *,
    rows: Sequence[Mapping[str, Any]],
    driver: PageDriver,
    base_url: str,
    output_dir: Path,
    manifest_dir: Path,
    viewports: Sequence[str],
    locales: Sequence[str],
    themes: Sequence[str],
    delay_ms: int,
    timeout_s: float,
    generated_at: str,
    target: Mapping[str, Any],
    excluded: Sequence[Mapping[str, str]] = (),
    selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive every cell of every row sequentially. Returns manifest + smell payloads."""

    manifest_pages: list[dict[str, Any]] = []
    smell_pages: list[dict[str, Any]] = []
    # What this run actually wrote, recorded at the call site. The self-check
    # verifies its files from this ledger instead of enumerating the output
    # directory — see the module docstring §8 on why no glob lives here.
    written_pngs: set[str] = set()

    for row in rows:
        cells, axis_gaps = state_matrix(row, viewports=viewports, locales=locales, themes=themes)
        gaps: list[dict[str, Any]] = list(axis_gaps) + access_and_page_state_gaps()
        states: list[dict[str, Any]] = []
        captured: list[tuple[CaptureCell, CellObservation]] = []
        # Deduped per page in first-seen order: the same error from two assets is
        # two entries, the same error from one asset in six states is one.
        console_entries: list[dict[str, Any]] = []
        console_seen: set[tuple[str, str | None]] = set()
        failed_responses: list[dict[str, Any]] = []
        failed_seen: set[tuple[str, int]] = set()
        # A route that failed to load once is not hammered five more times; the
        # remaining cells are recorded as not attempted, with the load error.
        page_failure: str | None = None

        for position, cell in enumerate(cells):
            entry: dict[str, Any] = {
                "viewport": cell.viewport,
                "locale": cell.locale,
                "theme": cell.theme,
                "access": cell.access,
                "viewport_width": cell.width,
                "viewport_height": cell.height,
            }
            if page_failure is not None:
                entry.update(
                    {
                        "captured": False,
                        "reason": f"page load failed on an earlier state, remaining states not attempted: {page_failure}",
                    }
                )
                states.append(entry)
                continue

            url = page_url(base_url, cell.route)
            try:
                observation = driver.capture(url=url, cell=cell, timeout_s=timeout_s)
            except CaptureUnavailable:
                raise
            except Exception as exc:  # a broken page is an observation, not a crash
                observation = CellObservation(
                    cell_id=cell.cell_id, loaded=False, error=f"{type(exc).__name__}: {exc}"
                )

            if delay_ms > 0 and position < len(cells) - 1:
                time.sleep(delay_ms / 1000.0)

            if not observation.loaded:
                page_failure = observation.error or "page did not load"
                entry.update({"captured": False, "reason": page_failure})
                states.append(entry)
                continue

            png = observation.screenshot_png
            if not png:
                entry.update({"captured": False, "reason": "driver returned no screenshot bytes"})
                states.append(entry)
                continue

            path, digest = write_screenshot(png, output_dir)
            written_pngs.add(path.name)
            dimensions = _png_dimensions(png)
            entry.update(
                {
                    "captured": True,
                    "file": os.path.relpath(path, manifest_dir).replace(os.sep, "/"),
                    "sha256": digest,
                    "bytes": len(png),
                    "width": dimensions[0] if dimensions else None,
                    "height": dimensions[1] if dimensions else None,
                    "applied_theme": observation.applied_theme,
                    "applied_locale": observation.applied_locale,
                }
            )
            if observation.applied_theme not in (None, cell.theme) or observation.applied_locale not in (
                None,
                cell.locale,
            ):
                # The page's own toggle refused the requested state. Say so rather
                # than filing the screenshot under a state it does not show.
                gaps.append(
                    {
                        "dimension": "state_application",
                        "value": f"{cell.viewport}/{cell.locale}/{cell.theme}",
                        "captured": True,
                        "reason": (
                            f"page settled on theme={observation.applied_theme!r} "
                            f"locale={observation.applied_locale!r}"
                        ),
                    }
                )
            states.append(entry)
            captured.append((cell, observation))
            for error in observation.console_errors:
                text = str(error.get("text") or "")
                source_url = error.get("source_url") or None
                key = (text, source_url)
                if key in console_seen:
                    continue
                console_seen.add(key)
                console_entries.append({"text": text, "source_url": source_url})
            for failure in observation.failed_responses:
                url = str(failure.get("url") or "")
                status = int(failure.get("status") or 0)
                if (url, status) in failed_seen:
                    continue
                failed_seen.add((url, status))
                failed_responses.append({"url": url, "status": status})

        metrics = _page_metrics(captured, attempted=len(cells), console_errors=console_entries)
        page_payload = {
            "page_id": row["page_id"],
            "route": row["capture_route"],
            "registry_route": row.get("route") or row["capture_route"],
            "route_kind": row.get("route_kind") or "",
            "states": states,
            "metrics": metrics,
            "console_errors": [dict(entry) for entry in console_entries],
            "failed_responses": [dict(entry) for entry in failed_responses],
            "gaps": gaps,
        }
        manifest_pages.append(page_payload)
        smell_pages.append(
            {
                "page_id": row["page_id"],
                "route": row["capture_route"],
                "metrics": metrics,
            }
        )

    attempted_total = sum(len(page["states"]) for page in manifest_pages)
    captured_total = sum(
        1 for page in manifest_pages for state in page["states"] if state.get("captured")
    )
    outcome = OUTCOME_CAPTURED
    if any(all(not state.get("captured") for state in page["states"]) for page in manifest_pages):
        outcome = OUTCOME_PARTIAL
    if manifest_pages and captured_total == 0:
        outcome = OUTCOME_PARTIAL

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_at": generated_at,
        "tool": {
            "module_ref": MODULE_REF,
            "version": TOOL_VERSION,
            "module_sha256": module_source_sha256(),
            "user_agent": USER_AGENT,
        },
        "target": dict(target),
        "axes": {
            "viewports": {name: list(VIEWPORTS[name]) for name in viewports},
            "locales": list(locales),
            "themes": list(themes),
            "access": [ACCESS_ANONYMOUS],
        },
        "selection": dict(selection or {}),
        "excluded": [dict(item) for item in excluded],
        "outcome": outcome,
        "totals": {
            "pages": len(manifest_pages),
            "states_attempted": attempted_total,
            "states_captured": captured_total,
        },
        "honesty": {
            "access": "anonymous only; no credential is entered, stored, or synthesized, so no premium payload can enter these artifacts",
            "gaps": "states that were not captured are recorded with a reason; nothing is inferred for them",
            "authority": "this tool measures and screenshots; it scores, ranks, and judges nothing",
        },
        "pages": manifest_pages,
    }

    smells = {
        "schema": SMELL_SCHEMA,
        "generated_at": generated_at,
        "tool": {"module_ref": MODULE_REF, "version": TOOL_VERSION},
        "target": dict(target),
        "disclaimer": MD_DISCLAIMER,
        "metric_notes": dict(METRIC_NOTES),
        "pages": smell_pages,
    }
    # ``written_pngs`` is a run receipt, not manifest content: the self-check
    # byte-compares two manifests, and the file set is not part of the schema.
    return {"manifest": manifest, "smells": smells, "written_pngs": sorted(written_pngs)}


# ---------------------------------------------------------------------------
# markdown emitter
# ---------------------------------------------------------------------------


def render_markdown(smells: Mapping[str, Any]) -> str:
    rows = sorted(smells.get("pages") or [], key=lambda page: (page.get("route") or "", page.get("page_id") or ""))
    lines = [
        "# Page evidence — measured facts",
        "",
        f"_{MD_DISCLAIMER}_",
        "",
        f"Generated {smells.get('generated_at')} · schema `{smells.get('schema')}`",
        "",
        "| route | page_id | words | h1 | panels | height px | h-overflow | slug hits | TODO hits | as-of | source | shots |",
        "| --- | --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | :---: | :---: | ---: |",
    ]

    def cell(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    for page in rows:
        metrics = page.get("metrics") or {}
        headings = metrics.get("heading_counts") or {}
        lines.append(
            "| {route} | {page_id} | {words} | {h1} | {panels} | {height} | {overflow} | {slugs} | {todos} | {asof} | {source} | {shots} |".format(
                route=page.get("route", ""),
                page_id=page.get("page_id", ""),
                words=cell(metrics.get("visible_word_count")),
                h1=cell(headings.get("h1")),
                panels=cell(metrics.get("panel_count")),
                height=cell(metrics.get("document_height_px")),
                overflow=cell(metrics.get("horizontal_overflow")),
                slugs=cell(metrics.get("raw_slug_hit_count")),
                todos=cell(metrics.get("todo_placeholder_hit_count")),
                asof=cell(metrics.get("asof_present")),
                source=cell(metrics.get("source_present")),
                shots=cell(metrics.get("screenshot_completion")),
            )
        )

    lines.extend(["", "## Metric notes", ""])
    for key in sorted(smells.get("metric_notes") or {}):
        lines.append(f"- **{key}** — {smells['metric_notes'][key]}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# local site server (light_mode_sweep pattern)
# ---------------------------------------------------------------------------


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # noqa: D102 - silence per-request noise
        return


def serve_site_dir(site_dir: Path) -> tuple[socketserver.TCPServer, int]:
    """Serve a built site on an ephemeral loopback port. Threaded: a page fans out."""

    handler = functools.partial(_QuietHandler, directory=str(site_dir))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


# ---------------------------------------------------------------------------
# playwright driver (lazily imported; never at module scope)
# ---------------------------------------------------------------------------

# Seeded BEFORE any page script runs. theme.js re-derives the theme from the hour
# when localStorage.themeAuto === '1' (its boot lift), which would silently
# override an attribute stamp — so the seed clears themeAuto, exactly the way the
# site's own setTheme() does on an explicit choice.
_STATE_SEED_SCRIPT = """
(state) => {
  try {
    localStorage.setItem('theme', state.theme);
    localStorage.removeItem('themeAuto');
    localStorage.setItem('lang', state.locale);
  } catch (e) {}
}
"""

# Applied AFTER load through the page's own toggle when it exposes one, so the
# capture goes through the same code path a user's click does (theme.js sets
# data-theme / data-lang on <html>, syncs documentElement.lang, and fires the
# themechange / langchange events the widgets listen for).
_APPLY_STATE_SCRIPT = """
(state) => {
  const docEl = document.documentElement;
  if (typeof window.setTheme === 'function') { window.setTheme(state.theme); }
  else {
    docEl.setAttribute('data-theme', state.theme);
    try { localStorage.setItem('theme', state.theme); localStorage.removeItem('themeAuto'); } catch (e) {}
  }
  if (typeof window.setLang === 'function') { window.setLang(state.locale); }
  else {
    docEl.setAttribute('data-lang', state.locale);
    try { docEl.lang = state.locale === 'zh' ? 'zh-CN' : 'en'; } catch (e) {}
    try { localStorage.setItem('lang', state.locale); } catch (e) {}
  }
  return {
    theme: docEl.getAttribute('data-theme'),
    locale: docEl.getAttribute('data-lang') || 'en',
  };
}
"""

# One observer, one page load, one JSON blob. Every number here is a count of
# something a human could count by hand; none of them is combined into a score.
# innerText is layout-aware, so the estate's same-DOM bilingual spans (.l-en /
# .l-zh, hidden by CSS off data-lang) are excluded automatically for the locale
# that is not showing — which is why the text metrics use innerText, not
# textContent.
_OBSERVER_SCRIPT = r"""
(cfg) => {
  const docEl = document.documentElement;
  const vw = docEl.clientWidth;
  const isVisible = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') === 0) return false;
    return el.getClientRects().length > 0;
  };
  const textOf = (el) => ((el && el.innerText) || '').trim();
  const bodyText = textOf(document.body);
  const lowerBody = bodyText.toLowerCase();

  const mainEl = document.querySelector('main');
  const sectionCount =
    document.querySelectorAll('body > section').length + (mainEl ? mainEl.children.length : 0);

  const headingCounts = {};
  const headingTexts = [];
  for (let level = 1; level <= 6; level += 1) {
    const nodes = Array.from(document.querySelectorAll('h' + level)).filter(isVisible);
    headingCounts['h' + level] = nodes.length;
    nodes.forEach((node) => {
      const t = textOf(node);
      if (t) headingTexts.push(t.toLowerCase());
    });
  }
  const seen = new Map();
  headingTexts.forEach((t) => seen.set(t, (seen.get(t) || 0) + 1));
  const duplicates = Array.from(seen.entries())
    .filter(([, count]) => count > 1)
    .map(([t]) => t)
    .sort();

  const panelSelector = (cfg.panel_selectors || []).join(',');
  const panelCount = panelSelector
    ? Array.from(document.querySelectorAll(panelSelector)).filter(isVisible).length
    : 0;

  const words = bodyText.split(/\s+/).filter(Boolean);
  const longParagraphs = Array.from(document.querySelectorAll('p'))
    .filter(isVisible)
    .filter((p) => textOf(p).split(/\s+/).filter(Boolean).length > (cfg.long_paragraph_words || 120))
    .length;

  const cap = cfg.max_hit_samples || 25;
  const slugMatches = bodyText.match(/\b[a-z][a-z0-9]+(?:_[a-z0-9]+){2,}\b/g) || [];
  const slugDistinct = Array.from(new Set(slugMatches)).sort();
  const todoMatches = bodyText.match(/TODO|FIXME|PLACEHOLDER|lorem ipsum/gi) || [];
  const todoDistinct = Array.from(new Set(todoMatches.map((m) => m.toLowerCase()))).sort();

  const widerThanViewport = Array.from(document.querySelectorAll('*')).filter((el) => {
    if (!isVisible(el)) return false;
    return el.getBoundingClientRect().width > vw + 1;
  }).length;

  const probe = (spec) => {
    if (!spec) return false;
    const selectors = (spec.selectors || []).join(',');
    if (selectors && Array.from(document.querySelectorAll(selectors)).some(isVisible)) return true;
    return (spec.text_patterns || []).some((p) => lowerBody.includes(String(p).toLowerCase()));
  };

  return {
    document_height_px: docEl.scrollHeight,
    section_count: sectionCount,
    heading_counts: headingCounts,
    duplicate_heading_texts: duplicates.slice(0, cap),
    panel_count: panelCount,
    visible_word_count: words.length,
    long_paragraph_count: longParagraphs,
    raw_slug_hits: slugDistinct.slice(0, cap),
    raw_slug_hit_count: slugDistinct.length,
    todo_placeholder_hits: todoDistinct.slice(0, cap),
    todo_placeholder_hit_count: todoDistinct.length,
    horizontal_overflow: docEl.scrollWidth > docEl.clientWidth,
    elements_wider_than_viewport: widerThanViewport,
    asof_present: probe(cfg.asof_probe),
    source_present: probe(cfg.source_probe),
  };
}
"""


def playwright_page_driver(
    *,
    headless: bool = True,
    user_agent: str = USER_AGENT,
    observer_config: Mapping[str, Any] | None = None,
    settle_ms: int = 400,
) -> PageDriver:  # pragma: no cover - needs a browser
    """Build the real driver. Imported lazily; a missing browser raises, never passes."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise CaptureUnavailable(
            f"playwright is not importable: {exc}. Install with: {INSTALL_HINT}"
        ) from exc

    try:
        manager = sync_playwright().start()
    except Exception as exc:
        raise CaptureUnavailable(
            f"playwright runtime is unavailable: {exc}. Install with: {INSTALL_HINT}"
        ) from exc
    try:
        browser = manager.chromium.launch(headless=headless)
    except Exception as exc:
        manager.stop()
        raise CaptureUnavailable(
            f"no chromium binary is installed: {exc}. Install with: {INSTALL_HINT}"
        ) from exc
    return _PlaywrightDriver(manager, browser, user_agent, dict(observer_config or DEFAULT_OBSERVER_CONFIG), settle_ms)


class _PlaywrightDriver:  # pragma: no cover - needs a browser
    """Thin adapter. It reports what it saw; it decides nothing about the page."""

    def __init__(
        self,
        manager: Any,
        browser: Any,
        user_agent: str,
        observer_config: Mapping[str, Any],
        settle_ms: int,
    ) -> None:
        self._manager = manager
        self._browser = browser
        self._user_agent = user_agent
        self._observer_config = observer_config
        self._settle_ms = settle_ms

    def capture(self, *, url: str, cell: CaptureCell, timeout_s: float) -> CellObservation:
        state = {"theme": cell.theme, "locale": cell.locale}
        context = self._browser.new_context(
            viewport={"width": cell.width, "height": cell.height},
            user_agent=self._user_agent,
            locale="zh-CN" if cell.locale == "zh" else "en-US",
            color_scheme=cell.theme,
            device_scale_factor=1,
        )
        # add_init_script takes source, not (fn, arg) — so the seed is wrapped as an
        # IIFE with the state literal baked in.
        context.add_init_script(f"({_STATE_SEED_SCRIPT.strip()})({json.dumps(state)})")
        page = context.new_page()
        console_errors: list[dict[str, Any]] = []
        failed_responses: list[dict[str, Any]] = []
        counters = {"requests": 0, "bytes": 0}

        def _on_console(msg: Any) -> None:
            if msg.type != "error":
                return
            # msg.location is a dict in the sync API, but a console message can
            # arrive without one; an unattributed error is recorded as such rather
            # than dropped.
            try:
                source_url = (msg.location or {}).get("url") or None
            except Exception:
                source_url = None
            console_errors.append({"text": msg.text, "source_url": source_url})

        def _on_response(response: Any) -> None:
            try:
                if response.status >= 400:
                    failed_responses.append(
                        {"url": response.url, "status": int(response.status)}
                    )
            except Exception:
                # A response object the driver cannot read is not evidence of a
                # failure; it is simply not recorded.
                pass

        page.on("console", _on_console)
        # A pageerror is an uncaught exception, not a resource: it has no URL, and
        # claiming one would be a fabricated attribution.
        page.on("pageerror", lambda err: console_errors.append({"text": f"pageerror: {err}", "source_url": None}))
        page.on("response", _on_response)
        page.on("request", lambda _req: counters.__setitem__("requests", counters["requests"] + 1))

        def _on_finished(request: Any) -> None:
            try:
                counters["bytes"] += int(request.sizes().get("responseBodySize") or 0)
            except Exception:
                # A response the driver cannot size is simply not counted; the
                # metric note says payload_bytes_total excludes them.
                pass

        page.on("requestfinished", _on_finished)
        try:
            response = page.goto(url, wait_until="load", timeout=timeout_s * 1000)
            if response is None:
                return CellObservation(cell_id=cell.cell_id, loaded=False, error="no response")
            if not response.ok:
                return CellObservation(
                    cell_id=cell.cell_id, loaded=False, error=f"HTTP {response.status}"
                )
            page.wait_for_timeout(self._settle_ms)
            applied = page.evaluate(_APPLY_STATE_SCRIPT.strip(), state) or {}
            page.wait_for_timeout(self._settle_ms)
            observed = page.evaluate(_OBSERVER_SCRIPT.strip(), dict(self._observer_config)) or {}
            screenshot = page.screenshot(full_page=True)
            return CellObservation(
                cell_id=cell.cell_id,
                loaded=True,
                screenshot_png=screenshot,
                observed=observed,
                console_errors=tuple(console_errors),
                failed_responses=tuple(failed_responses),
                request_count=int(counters["requests"]),
                payload_bytes_total=int(counters["bytes"]),
                applied_theme=applied.get("theme"),
                applied_locale=applied.get("locale"),
            )
        except Exception as exc:
            return CellObservation(
                cell_id=cell.cell_id, loaded=False, error=f"{type(exc).__name__}: {exc}"
            )
        finally:
            context.close()

    def close(self) -> None:
        self._browser.close()
        self._manager.stop()


# ---------------------------------------------------------------------------
# self-check
# ---------------------------------------------------------------------------


def _tiny_png(width: int, height: int, fill: int) -> bytes:
    """A real PNG (valid IHDR) so content-addressing and dimension reads are exercised."""

    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([fill, fill, fill]) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(
        b"IEND", b""
    )


class _SelfCheckDriver:
    """Canned observations. Opens no browser, no socket, no page."""

    def capture(self, *, url: str, cell: CaptureCell, timeout_s: float) -> CellObservation:
        return CellObservation(
            cell_id=cell.cell_id,
            loaded=True,
            screenshot_png=_tiny_png(4, 3, 7 if cell.theme == "dark" else 240),
            observed={
                "document_height_px": 3200,
                "section_count": 6,
                "heading_counts": {"h1": 1, "h2": 4, "h3": 2, "h4": 0, "h5": 0, "h6": 0},
                "duplicate_heading_texts": [],
                "panel_count": 9,
                "visible_word_count": 812,
                "long_paragraph_count": 1,
                "raw_slug_hits": ["regime_state_score"],
                "raw_slug_hit_count": 1,
                "todo_placeholder_hits": [],
                "todo_placeholder_hit_count": 0,
                "horizontal_overflow": False,
                "elements_wider_than_viewport": 0,
                "asof_present": True,
                "source_present": False,
            },
            # Attributed console error + a failing response, so the self-check
            # exercises the attribution path end to end and not just the shape.
            console_errors=(
                {"text": "TypeError: canned", "source_url": "http://127.0.0.1:0/assets/canned.js"},
            ),
            failed_responses=({"url": "http://127.0.0.1:0/api/canned", "status": 401},),
            request_count=31,
            payload_bytes_total=812_345,
            applied_theme=cell.theme,
            applied_locale=cell.locale,
        )


def self_check() -> tuple[bool, dict[str, Any]]:
    """Prove the pipeline end to end with a canned driver: no browser, no network."""

    rows = [
        {
            "page_id": "macro",
            "route": "/macro.html",
            "capture_route": "/macro.html",
            "repo": "macro",
            "priority": "P0",
            "route_kind": "static",
            "is_family": False,
            "exemplar": None,
            "themes": None,
            "locales": None,
        },
        {
            "page_id": "dark_only",
            "route": "/terminal.html",
            "capture_route": "/terminal.html",
            "repo": "macro",
            "priority": "P0",
            "route_kind": "static",
            "is_family": False,
            "exemplar": None,
            "themes": ("dark",),
            "locales": ("en",),
        },
    ]
    findings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "evidence"
        payloads = [
            run_capture(
                rows=rows,
                driver=_SelfCheckDriver(),
                base_url="http://127.0.0.1:0",
                output_dir=output_dir,
                manifest_dir=root,
                viewports=("desktop", "mobile"),
                locales=("en", "zh"),
                themes=("light", "dark"),
                delay_ms=0,
                timeout_s=5,
                generated_at="2026-01-01T00:00:00Z",
                target={"kind": "self_check", "base_url": None, "site_dir": None, "resolved_sha_or_none": None},
                selection={"mode": "registry", "priority": "P0", "repo": "macro"},
            )
            for _ in range(2)
        ]
        manifest = payloads[0]["manifest"]

        if canonical_json_bytes(payloads[0]["manifest"]) != canonical_json_bytes(payloads[1]["manifest"]):
            findings.append("two runs with a pinned as-of produced different manifests")

        pages = {page["page_id"]: page for page in manifest["pages"]}
        dark_only = pages.get("dark_only")
        if dark_only is None:
            findings.append("dark_only page missing from the manifest")
        else:
            if any(state["theme"] == "light" for state in dark_only["states"]):
                findings.append("registry-declared dark-only page produced a light state")
            if any(state["locale"] == "zh" for state in dark_only["states"]):
                findings.append("registry-declared en-only page produced a zh state")
            gap_values = {gap["value"] for gap in dark_only["gaps"]}
            if not {"light", "zh"} <= gap_values:
                findings.append("excluded axes were not recorded as gaps")

        for page in manifest["pages"]:
            missing = [key for key in METRIC_KEYS if key not in page["metrics"]]
            if missing:
                findings.append(f"{page['page_id']}: metrics missing {missing}")
            access_gaps = {gap["value"] for gap in page["gaps"] if gap["dimension"] == "access"}
            if set(GATED_ACCESS_STATES) - access_gaps:
                findings.append(f"{page['page_id']}: gated access states not recorded as gaps")
            if any(state.get("access") != ACCESS_ANONYMOUS for state in page["states"]):
                findings.append(f"{page['page_id']}: a state claims a non-anonymous access tier")
            if not all(
                set(error) == {"text", "source_url"} for error in page["console_errors"]
            ):
                findings.append(f"{page['page_id']}: a console error lost its attribution shape")
            if not all(
                set(failure) == {"url", "status"} for failure in page["failed_responses"]
            ):
                findings.append(f"{page['page_id']}: a failed response lost its url/status shape")

        # Content-addressing is checked against the run's own write ledger and the
        # paths the manifest names — never by enumerating the directory (docstring
        # §8). Reading a known path is fine; discovering one is the opaque edge.
        shas = {
            state["sha256"]
            for page in manifest["pages"]
            for state in page["states"]
            if state.get("captured")
        }
        expected = {f"{sha[:16]}.png" for sha in shas}
        if len(expected) != len(shas):
            findings.append(
                f"{len(shas)} distinct digests collapse onto {len(expected)} file names: "
                "the 16-hex prefix collided"
            )
        for index, payload in enumerate(payloads, start=1):
            if set(payload["written_pngs"]) != expected:
                findings.append(
                    f"run {index} wrote {sorted(payload['written_pngs'])}, "
                    f"the manifest names {sorted(expected)}"
                )
        for page in manifest["pages"]:
            for state in page["states"]:
                if not state.get("captured"):
                    continue
                name = Path(state["file"]).name
                try:
                    body = (output_dir / name).read_bytes()
                except OSError as exc:
                    findings.append(f"{name}: the file this state names is unreadable: {exc}")
                    continue
                digest = hashlib.sha256(body).hexdigest()
                if name != f"{digest[:16]}.png":
                    findings.append(f"{name} is not addressed by its own content")
                if digest != state["sha256"]:
                    findings.append(
                        f"{name}: manifest digest {state['sha256'][:16]} does not match the bytes on disk"
                    )

        markdown = render_markdown(payloads[0]["smells"])
        if MD_DISCLAIMER not in markdown:
            findings.append("markdown emitter dropped the disclaimer")

    summary = {
        "module_ref": MODULE_REF,
        "version": TOOL_VERSION,
        "module_sha256": module_source_sha256(),
        "manifest_schema": MANIFEST_SCHEMA,
        "smell_schema": SMELL_SCHEMA,
        "registry_schema_expected": REGISTRY_SCHEMA,
        "viewports": {name: list(dims) for name, dims in VIEWPORTS.items()},
        "locales": list(SUPPORTED_LOCALES),
        "themes": list(SUPPORTED_THEMES),
        "access_captured": [ACCESS_ANONYMOUS],
        "access_gaps": {state: GATED_ACCESS_REASON for state in GATED_ACCESS_STATES},
        "page_state_gaps": {state: SYNTHETIC_PAGE_STATE_REASON for state in SYNTHETIC_PAGE_STATES},
        "metrics": list(METRIC_KEYS),
        "user_agent": USER_AGENT,
        "findings": findings,
        "ok": not findings,
    }
    return not findings, summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _csv_list(raw: str, allowed: Sequence[str], flag: str) -> list[str]:
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise argparse.ArgumentTypeError(f"{flag}: unknown value(s) {unknown}; allowed {list(allowed)}")
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--priority", default="P0")
    parser.add_argument("--repo", default="macro")
    parser.add_argument("--base-url", help="live origin to capture against")
    parser.add_argument("--site-dir", help="built site directory to serve locally")
    parser.add_argument("--routes", help="comma list of routes; overrides registry selection")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--smells", default=DEFAULT_SMELLS)
    parser.add_argument("--emit-md", help="also render the smell report as a markdown table")
    parser.add_argument("--viewports", default="desktop,tablet,mobile")
    parser.add_argument("--locales", default="en,zh")
    parser.add_argument("--themes", default="light,dark")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--delay-ms", type=int, default=500, help="politeness sleep between page loads")
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--as-of", help="pin generated_at (ISO); makes a run byte-reproducible")
    parser.add_argument(
        "--observer-config", help="JSON file overriding panel selectors / probes / caps"
    )
    parser.add_argument("--headed", action="store_true", help="run the browser headed")
    parser.add_argument("--self-check", action="store_true", help="canned end-to-end proof; opens no browser")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    driver_factory: Callable[..., PageDriver] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check:
        ok, summary = self_check()
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        if not ok:
            print(
                "::error title=capture-page-evidence::self-check failed: "
                + "; ".join(summary["findings"]),
                flush=True,
            )
            return 1
        return EXIT_OK

    try:
        viewports = _csv_list(args.viewports, tuple(VIEWPORTS), "--viewports")
        locales = _csv_list(args.locales, SUPPORTED_LOCALES, "--locales")
        themes = _csv_list(args.themes, SUPPORTED_THEMES, "--themes")
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not (viewports and locales and themes):
        print("error: --viewports, --locales and --themes each need at least one value", file=sys.stderr)
        return EXIT_USAGE

    if bool(args.base_url) == bool(args.site_dir):
        print("error: pass exactly one of --base-url or --site-dir", file=sys.stderr)
        return EXIT_USAGE

    observer_config = dict(DEFAULT_OBSERVER_CONFIG)
    if args.observer_config:
        try:
            observer_config.update(json.loads(Path(args.observer_config).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: --observer-config is not readable JSON: {exc}", file=sys.stderr)
            return EXIT_USAGE

    explicit_routes = [part.strip() for part in (args.routes or "").split(",") if part.strip()]
    registry_path = Path(args.registry)
    registry_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    try:
        if explicit_routes and not registry_path.exists():
            # Pure override mode: no registry on disk, minimal rows synthesized.
            rows = synthesize_rows(explicit_routes, [])
        else:
            registry_rows = load_registry(registry_path)
            if explicit_routes:
                rows = synthesize_rows(explicit_routes, registry_rows)
            else:
                rows, excluded = select_rows(
                    registry_rows,
                    priority=args.priority,
                    repo=args.repo,
                    max_pages=args.max_pages,
                )
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.max_pages > 0 and len(rows) > args.max_pages:
        for row in rows[args.max_pages :]:
            excluded.append(
                {"page_id": row["page_id"], "reason": f"beyond the --max-pages cap of {args.max_pages}"}
            )
        rows = rows[: args.max_pages]

    if not rows:
        print(
            "::warning title=capture-page-evidence::no page matched the selection "
            f"(priority={args.priority!r} repo={args.repo!r}); nothing captured",
            flush=True,
        )
        return EXIT_USAGE

    httpd: socketserver.TCPServer | None = None
    if args.site_dir:
        site_dir = Path(args.site_dir).resolve()
        if not site_dir.is_dir():
            print(f"error: --site-dir is not a directory: {site_dir}", file=sys.stderr)
            return EXIT_USAGE
        httpd, port = serve_site_dir(site_dir)
        base_url = f"http://127.0.0.1:{port}"
        target = {
            "kind": "site_dir",
            "base_url": None,
            "site_dir": str(site_dir),
            "resolved_sha_or_none": _git_head_sha(site_dir),
            "resolved_sha_source": "git HEAD of the checkout that produced --site-dir",
        }
    else:
        base_url = str(args.base_url)
        target = {
            "kind": "base_url",
            "base_url": base_url,
            "site_dir": None,
            "resolved_sha_or_none": None,
            "resolved_sha_source": "unavailable: a live origin does not disclose the commit it is serving",
        }

    factory = driver_factory or playwright_page_driver
    try:
        driver = factory(
            headless=not args.headed,
            user_agent=USER_AGENT,
            observer_config=observer_config,
        )
    except CaptureUnavailable as exc:
        if httpd is not None:
            httpd.shutdown()
        print(
            f"::error title=capture-page-evidence::{OUTCOME_UNAVAILABLE}: {exc}",
            flush=True,
        )
        print(
            json.dumps(
                {
                    "outcome": OUTCOME_UNAVAILABLE,
                    "reason": str(exc),
                    "install": INSTALL_HINT,
                    "artifacts_written": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_UNAVAILABLE

    manifest_path = Path(args.manifest)
    smells_path = Path(args.smells)
    # What actually selected these pages. Under --routes the registry filters never
    # ran, so priority/repo are null with the reason attached rather than echoing
    # parser defaults — a manifest that claims repo "macro" while capturing another
    # origin is a false provenance claim, which is exactly what this tool refuses.
    selection: dict[str, Any] = {
        "max_pages": args.max_pages,
        "registry": str(registry_path),
        "registry_rows": len(registry_rows),
        "explicit_routes": explicit_routes,
        "selected": len(rows),
    }
    if explicit_routes:
        selection.update(
            {"mode": "explicit_routes", "priority": None, "repo": None, "note": ROUTES_SELECTION_NOTE}
        )
    else:
        selection.update({"mode": "registry", "priority": args.priority, "repo": args.repo})
    try:
        payloads = run_capture(
            rows=rows,
            driver=driver,
            base_url=base_url,
            output_dir=Path(args.output_dir),
            manifest_dir=manifest_path.parent if str(manifest_path.parent) else Path("."),
            viewports=viewports,
            locales=locales,
            themes=themes,
            delay_ms=max(0, args.delay_ms),
            timeout_s=args.timeout_s,
            generated_at=(args.as_of or _utc_now()),
            target=target,
            excluded=excluded,
            selection=selection,
        )
    finally:
        close = getattr(driver, "close", None)
        if callable(close):
            close()
        if httpd is not None:
            httpd.shutdown()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_json_bytes(payloads["manifest"]))
    smells_path.parent.mkdir(parents=True, exist_ok=True)
    smells_path.write_bytes(canonical_json_bytes(payloads["smells"]))
    if args.emit_md:
        md_path = Path(args.emit_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(payloads["smells"]), encoding="utf-8")

    totals = payloads["manifest"]["totals"]
    print(f"outcome: {payloads['manifest']['outcome']}")
    print(f"pages: {totals['pages']}  states: {totals['states_captured']}/{totals['states_attempted']} captured")
    print(f"manifest: {manifest_path}")
    print(f"smells: {smells_path}")
    if args.emit_md:
        print(f"markdown: {args.emit_md}")

    blind_pages = [
        page["page_id"]
        for page in payloads["manifest"]["pages"]
        if not any(state.get("captured") for state in page["states"])
    ]
    if blind_pages:
        print(
            "::warning title=capture-page-evidence::captured no state at all for: "
            + ", ".join(blind_pages),
            flush=True,
        )
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
