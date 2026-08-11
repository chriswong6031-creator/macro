"""Hermetic tests for the page evidence capture harness.

No test here opens a browser, a socket, or a file outside ``tmp_path``. The page
driver is an injected fake through the same seam production uses, exactly the way
``test_biocatalyst_browser_verifier`` injects a scripted observer.

``pytest.importorskip("playwright")`` is deliberately absent: CI installs minimal
deps and playwright is not a repo dependency, so an importorskip here would SKIP
green forever and prove nothing. What is under test is the harness's bookkeeping —
which states it expands, which it refuses to fake, and what it writes down.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "capture_page_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("capture_page_evidence_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves ``cls.__module__`` through ``sys.modules``; a
    # file-loaded module absent from it raises on the first ``@dataclass``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cpe = _load_module()


def _png(width: int, height: int, fill: int) -> bytes:
    """A real PNG, so IHDR dimension reads and content-addressing are exercised."""

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


OBSERVED = {
    "document_height_px": 4210,
    "section_count": 7,
    "heading_counts": {"h1": 1, "h2": 5, "h3": 3, "h4": 0, "h5": 0, "h6": 0},
    "duplicate_heading_texts": ["what to watch"],
    "panel_count": 12,
    "visible_word_count": 1440,
    "long_paragraph_count": 2,
    "raw_slug_hits": ["regime_state_score", "carry_z_score"],
    "raw_slug_hit_count": 2,
    "todo_placeholder_hits": ["todo"],
    "todo_placeholder_hit_count": 1,
    "horizontal_overflow": True,
    "elements_wider_than_viewport": 4,
    "asof_present": True,
    "source_present": False,
}


class FakeDriver:
    """In-memory driver. Same seam as ``playwright_page_driver``; no browser."""

    def __init__(
        self,
        *,
        observed: dict[str, Any] | None = None,
        fail_routes: tuple[str, ...] = (),
        per_theme_bytes: bool = False,
        applied_override: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._observed = dict(observed or OBSERVED)
        self._fail_routes = fail_routes
        self._per_theme_bytes = per_theme_bytes
        self._applied_override = applied_override or {}
        self.closed = False

    def capture(self, *, url: str, cell, timeout_s: float):
        self.calls.append((url, cell.cell_id))
        if any(route in url for route in self._fail_routes):
            raise TimeoutError(f"navigation timed out after {timeout_s}s")
        fill = (7 if cell.theme == "dark" else 240) if self._per_theme_bytes else 128
        return cpe.CellObservation(
            cell_id=cell.cell_id,
            loaded=True,
            screenshot_png=_png(6, 4, fill),
            observed=dict(self._observed),
            console_errors=("TypeError: x is not a function",),
            request_count=41,
            payload_bytes_total=1_234_567,
            applied_theme=self._applied_override.get("theme", cell.theme),
            applied_locale=self._applied_override.get("locale", cell.locale),
        )

    def close(self) -> None:
        self.closed = True


REGISTRY_DOC = {
    "schema": "mastermind.page_registry.v1",
    "generated_at": "2026-08-11T00:00:00Z",
    "pages": [
        {
            "page_id": "macro",
            "repo": "macro",
            "route": "/macro.html",
            "priority": "P0",
            "route_kind": "static",
            "themes": ["light", "dark"],
            "locales": ["en", "zh"],
        },
        {
            "page_id": "terminal",
            "repo": "macro",
            "route": "/terminal.html",
            "priority": "P0",
            "route_kind": "static",
            "themes": ["dark"],
            "locales": ["en"],
        },
        {
            "page_id": "stock_family",
            "repo": "macro",
            "route": "/stock.html#{TICKER}",
            "priority": "P0",
            "route_kind": "family",
        },
        {
            "page_id": "dossier_family",
            "repo": "macro",
            "route": "/dossier/{slug}.html",
            "priority": "P0",
            "route_kind": "family",
            "exemplar_route": "/dossier/nvda.html",
        },
        {
            "page_id": "charting_terminal",
            "repo": "charting-app",
            "route": "/terminal",
            "priority": "P0",
            "route_kind": "static",
        },
        {
            "page_id": "secondary",
            "repo": "macro",
            "route": "/zzz.html",
            "priority": "P1",
            "route_kind": "static",
        },
    ],
}


@pytest.fixture()
def registry(tmp_path: Path) -> Path:
    path = tmp_path / "page_registry.json"
    path.write_text(json.dumps(REGISTRY_DOC), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    registry: Path | str,
    driver: FakeDriver,
    *extra: str,
    manifest: str | None = None,
) -> tuple[int, dict[str, Any]]:
    manifest_path = Path(manifest) if manifest else tmp_path / "manifest.json"
    argv = [
        "--registry",
        str(registry),
        "--base-url",
        "http://capture.invalid",
        "--output-dir",
        str(tmp_path / "evidence"),
        "--manifest",
        str(manifest_path),
        "--smells",
        str(tmp_path / "smells.json"),
        "--delay-ms",
        "0",
        "--as-of",
        "2026-08-11T00:00:00Z",
        *extra,
    ]
    code = cpe.main(argv, driver_factory=lambda **_kwargs: driver)
    payload: dict[str, Any] = {}
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return code, payload


# --------------------------------------------------------------------------- #
# selection + state matrix
# --------------------------------------------------------------------------- #


def test_selection_filters_priority_repo_and_unexemplared_families(registry: Path):
    rows = cpe.load_registry(registry)
    selected, excluded = cpe.select_rows(rows, priority="P0", repo="macro", max_pages=30)
    assert [row["page_id"] for row in selected] == ["dossier_family", "macro", "terminal"]
    assert [row["capture_route"] for row in selected] == [
        "/dossier/nvda.html",
        "/macro.html",
        "/terminal.html",
    ]
    reasons = {item["page_id"]: item["reason"] for item in excluded}
    assert "stock_family" in reasons and "exemplar" in reasons["stock_family"]


def test_state_matrix_honors_registry_themes_and_locales(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    code, manifest = _run(tmp_path, registry, driver)
    assert code == cpe.EXIT_OK
    pages = {page["page_id"]: page for page in manifest["pages"]}

    dark_only = pages["terminal"]
    assert {state["theme"] for state in dark_only["states"]} == {"dark"}
    assert {state["locale"] for state in dark_only["states"]} == {"en"}
    axis_gaps = {
        (gap["dimension"], gap["value"]) for gap in dark_only["gaps"] if gap["dimension"] in {"theme", "locale"}
    }
    assert axis_gaps == {("theme", "light"), ("locale", "zh")}

    # A page the registry does not narrow gets the full requested matrix.
    assert len(pages["macro"]["states"]) == 3 * 2 * 2
    assert not [gap for gap in pages["macro"]["gaps"] if gap["dimension"] in {"theme", "locale"}]


def test_unknown_axis_sentinel_reads_as_silent_not_as_supports_nothing(tmp_path: Path):
    """The registry writes "unknown" for an axis it could not resolve.

    Reading that as "supports nothing" would expand to zero cells and hand back a
    page with no evidence at all — the opposite of what an evidence tool owes.
    """

    doc = {
        "schema": "mastermind.page_registry.v1",
        "pages": [
            {
                "page_id": "unresolved",
                "repo": "macro",
                "route": "/unresolved.html",
                "priority": "P0",
                "route_kind": "page",
                "themes": "unknown",
                "locales": "unknown",
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    row = cpe.normalize_row(doc["pages"][0], index=0)
    assert row["themes"] is None and row["locales"] is None

    _code, manifest = _run(tmp_path, path, FakeDriver(), "--viewports", "desktop")
    page = manifest["pages"][0]
    assert len(page["states"]) == 4, "an unresolved axis must still be attempted"
    assert not [gap for gap in page["gaps"] if gap["dimension"] in {"theme", "locale"}]


def test_family_row_captures_its_exemplar_route(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    _code, manifest = _run(tmp_path, registry, driver, "--viewports", "desktop")
    family = next(page for page in manifest["pages"] if page["page_id"] == "dossier_family")
    assert family["route"] == "/dossier/nvda.html"
    assert family["registry_route"] == "/dossier/{slug}.html"
    assert all("/dossier/nvda.html" in url for url, _cell in driver.calls if "dossier" in url)


def test_routes_override_without_a_registry_synthesizes_rows(tmp_path: Path):
    driver = FakeDriver()
    missing = tmp_path / "nope" / "page_registry.json"
    code, manifest = _run(
        tmp_path,
        missing,
        driver,
        "--routes",
        "/a.html,/b.html",
        "--viewports",
        "desktop",
        "--locales",
        "en",
        "--themes",
        "dark",
    )
    assert code == cpe.EXIT_OK
    assert [page["route"] for page in manifest["pages"]] == ["/a.html", "/b.html"]
    assert [page["page_id"] for page in manifest["pages"]] == ["a.html", "b.html"]
    # Nothing is narrowed by a registry that does not exist: the requested axes stand.
    assert all(len(page["states"]) == 1 for page in manifest["pages"])


def test_routes_override_reuses_a_matching_registry_row(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    _code, manifest = _run(
        tmp_path, registry, driver, "--routes", "/terminal.html", "--viewports", "desktop"
    )
    page = manifest["pages"][0]
    assert page["page_id"] == "terminal"
    assert {state["theme"] for state in page["states"]} == {"dark"}


def test_max_pages_caps_the_run(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    _code, manifest = _run(tmp_path, registry, driver, "--max-pages", "1", "--viewports", "desktop")
    assert len(manifest["pages"]) == 1
    assert any("max-pages" in item["reason"] for item in manifest["excluded"])


# --------------------------------------------------------------------------- #
# honesty: gaps, anonymity
# --------------------------------------------------------------------------- #


def test_gated_access_and_unsynthesizable_states_are_recorded_as_gaps(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    _code, manifest = _run(tmp_path, registry, driver, "--viewports", "desktop")
    for page in manifest["pages"]:
        access = {gap["value"]: gap for gap in page["gaps"] if gap["dimension"] == "access"}
        assert set(access) == set(cpe.GATED_ACCESS_STATES)
        assert all(gap["captured"] is False for gap in access.values())
        assert all(
            gap["reason"] == "requires authenticated session; not automatable without approved fixtures"
            for gap in access.values()
        )
        states = {gap["value"]: gap for gap in page["gaps"] if gap["dimension"] == "page_state"}
        assert set(states) == set(cpe.SYNTHETIC_PAGE_STATES)
        assert all(
            gap["reason"] == "state not synthesizable against static output" for gap in states.values()
        )
        # Everything actually captured is anonymous, and says so.
        assert {state["access"] for state in page["states"]} == {"anonymous"}


def test_state_the_page_refused_to_apply_is_disclosed(tmp_path: Path, registry: Path):
    driver = FakeDriver(applied_override={"theme": "light"})
    _code, manifest = _run(
        tmp_path, registry, driver, "--routes", "/terminal.html", "--viewports", "desktop"
    )
    page = manifest["pages"][0]
    state = page["states"][0]
    assert state["captured"] is True
    assert state["applied_theme"] == "light" and state["theme"] == "dark"
    mismatch = [gap for gap in page["gaps"] if gap["dimension"] == "state_application"]
    assert mismatch and "light" in mismatch[0]["reason"]


# --------------------------------------------------------------------------- #
# evidence files + metrics
# --------------------------------------------------------------------------- #


def test_identical_bytes_share_one_content_addressed_file(tmp_path: Path, registry: Path):
    driver = FakeDriver()  # same PNG for every cell
    _code, manifest = _run(tmp_path, registry, driver, "--routes", "/macro.html")
    page = manifest["pages"][0]
    captured = [state for state in page["states"] if state["captured"]]
    assert len(captured) == 12

    files = sorted((tmp_path / "evidence").glob("*.png"))
    assert len(files) == 1, "identical screenshot bytes must collapse onto one file"

    digest = hashlib.sha256(files[0].read_bytes()).hexdigest()
    assert files[0].name == f"{digest[:16]}.png"
    assert {state["sha256"] for state in captured} == {digest}
    assert {state["file"] for state in captured} == {f"evidence/{digest[:16]}.png"}
    assert {state["bytes"] for state in captured} == {files[0].stat().st_size}
    assert {(state["width"], state["height"]) for state in captured} == {(6, 4)}


def test_distinct_bytes_get_distinct_files(tmp_path: Path, registry: Path):
    driver = FakeDriver(per_theme_bytes=True)
    _code, _manifest = _run(
        tmp_path, registry, driver, "--routes", "/macro.html", "--viewports", "desktop", "--locales", "en"
    )
    assert len(sorted((tmp_path / "evidence").glob("*.png"))) == 2


def test_metrics_pass_through_the_observer_unchanged(tmp_path: Path, registry: Path):
    driver = FakeDriver()
    _code, manifest = _run(tmp_path, registry, driver, "--routes", "/macro.html")
    metrics = manifest["pages"][0]["metrics"]
    for key, value in OBSERVED.items():
        assert metrics[key] == value, key
    assert metrics["request_count"] == 41
    assert metrics["payload_bytes_total"] == 1_234_567
    assert metrics["console_error_count"] == 1
    assert metrics["screenshot_completion"] == 1.0
    assert metrics["measured_in"] == {
        "viewport": "desktop",
        "locale": "en",
        "theme": "light",
        "access": "anonymous",
    }
    assert set(metrics["by_viewport"]) == {"desktop", "tablet", "mobile"}
    assert manifest["pages"][0]["console_errors"] == ["TypeError: x is not a function"]


def test_no_metric_is_a_score_or_a_verdict(tmp_path: Path, registry: Path):
    _code, manifest = _run(tmp_path, registry, FakeDriver(), "--viewports", "desktop")
    banned = ("score", "grade", "rating", "rank", "severity", "verdict", "quality", "weight")
    for page in manifest["pages"]:
        for key in page["metrics"]:
            assert not any(word in key.lower() for word in banned), key


# --------------------------------------------------------------------------- #
# failure handling
# --------------------------------------------------------------------------- #


def test_a_failing_page_is_recorded_and_does_not_abort_the_run(tmp_path: Path, registry: Path):
    driver = FakeDriver(fail_routes=("/terminal.html",))
    code, manifest = _run(tmp_path, registry, driver, "--viewports", "desktop")
    assert code == cpe.EXIT_PARTIAL
    pages = {page["page_id"]: page for page in manifest["pages"]}

    broken = pages["terminal"]
    assert all(state["captured"] is False for state in broken["states"])
    assert "TimeoutError" in broken["states"][0]["reason"]
    assert broken["metrics"]["screenshot_completion"] == 0.0
    assert broken["metrics"]["document_height_px"] is None
    assert broken["metrics"]["measured_in"] is None

    # The rest of the run still happened.
    assert all(state["captured"] for state in pages["macro"]["states"])
    assert manifest["outcome"] == "partial"


def test_a_dead_route_is_not_hammered_for_every_remaining_state(tmp_path: Path, registry: Path):
    driver = FakeDriver(fail_routes=("/macro.html",))
    _code, manifest = _run(tmp_path, registry, driver, "--routes", "/macro.html")
    macro_calls = [call for call in driver.calls if "/macro.html" in call[0]]
    assert len(macro_calls) == 1, "one load failure is enough; politeness caps the retries"
    later = manifest["pages"][0]["states"][1]
    assert later["captured"] is False
    assert "not attempted" in later["reason"]


def test_missing_registry_is_a_clean_error_not_a_traceback(tmp_path: Path, capsys):
    code = cpe.main(
        [
            "--registry",
            str(tmp_path / "absent.json"),
            "--base-url",
            "http://capture.invalid",
            "--manifest",
            str(tmp_path / "m.json"),
            "--smells",
            str(tmp_path / "s.json"),
        ],
        driver_factory=lambda **_kwargs: FakeDriver(),
    )
    assert code == cpe.EXIT_USAGE
    err = capsys.readouterr().err
    assert "page registry not found" in err
    assert "Traceback" not in err
    assert not (tmp_path / "m.json").exists()


def test_no_browser_writes_no_artifact_and_exits_unavailable(tmp_path: Path, capsys):
    def _refuse(**_kwargs):
        raise cpe.CaptureUnavailable("no chromium binary is installed")

    manifest = tmp_path / "m.json"
    code = cpe.main(
        [
            "--registry",
            str(tmp_path / "absent.json"),
            "--routes",
            "/a.html",
            "--base-url",
            "http://capture.invalid",
            "--manifest",
            str(manifest),
            "--smells",
            str(tmp_path / "s.json"),
        ],
        driver_factory=_refuse,
    )
    assert code == cpe.EXIT_UNAVAILABLE
    out = capsys.readouterr().out
    assert "verifier_unavailable" in out
    assert "playwright install chromium" in out
    assert not manifest.exists(), "a no-browser run must never overwrite committed evidence"


def test_base_url_and_site_dir_are_mutually_exclusive(tmp_path: Path, capsys):
    code = cpe.main(["--routes", "/a.html"], driver_factory=lambda **_kwargs: FakeDriver())
    assert code == cpe.EXIT_USAGE
    assert "exactly one of --base-url or --site-dir" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# determinism + schema
# --------------------------------------------------------------------------- #


def test_as_of_pins_the_run_byte_for_byte(tmp_path: Path, registry: Path):
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    _run(tmp_path, registry, FakeDriver(), "--viewports", "desktop", manifest=str(first))
    _run(tmp_path, registry, FakeDriver(), "--viewports", "desktop", manifest=str(second))
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text())["generated_at"] == "2026-08-11T00:00:00Z"


def test_manifest_schema_is_complete(tmp_path: Path, registry: Path):
    _code, manifest = _run(tmp_path, registry, FakeDriver(fail_routes=("/terminal.html",)), "--viewports", "desktop")
    assert manifest["schema"] == "mastermind.p0_evidence.v1"
    for key in ("generated_at", "tool", "target", "axes", "selection", "excluded", "outcome", "totals", "honesty", "pages"):
        assert key in manifest, key
    assert set(manifest["target"]) >= {"base_url", "site_dir", "resolved_sha_or_none"}
    assert manifest["target"]["resolved_sha_or_none"] is None  # a live origin cannot be pinned

    for page in manifest["pages"]:
        for key in ("page_id", "route", "states", "metrics", "console_errors", "gaps"):
            assert key in page, key
        # Every metric key is present even for a page that captured nothing.
        assert set(cpe.METRIC_KEYS) <= set(page["metrics"])
        for state in page["states"]:
            assert set(state) >= {"viewport", "locale", "theme", "access", "captured"}
            if state["captured"]:
                assert set(state) >= {"file", "sha256", "bytes", "width", "height"}
            else:
                assert state["reason"]


def test_smell_report_carries_notes_and_no_interpretation(tmp_path: Path, registry: Path):
    _run(tmp_path, registry, FakeDriver(), "--viewports", "desktop")
    smells = json.loads((tmp_path / "smells.json").read_text(encoding="utf-8"))
    assert smells["schema"] == "mastermind.ux_smell_report.v1"
    assert smells["disclaimer"] == cpe.MD_DISCLAIMER
    assert "visible_word_count" in smells["metric_notes"]
    for page in smells["pages"]:
        assert set(page) == {"page_id", "route", "metrics"}


def test_markdown_leads_with_the_disclaimer_and_sorts_by_route(tmp_path: Path, registry: Path):
    md = tmp_path / "report.md"
    _run(tmp_path, registry, FakeDriver(), "--viewports", "desktop", "--emit-md", str(md))
    text = md.read_text(encoding="utf-8")
    assert cpe.MD_DISCLAIMER in text.split("| route |")[0]
    routes = [line.split("|")[1].strip() for line in text.splitlines() if line.startswith("| /")]
    assert routes == sorted(routes)


# --------------------------------------------------------------------------- #
# module contract
# --------------------------------------------------------------------------- #


def test_self_check_passes():
    assert cpe.main(["--self-check"]) == 0


def test_playwright_is_imported_only_inside_the_driver_factory():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    def _playwright_imports(node: ast.AST) -> list[int]:
        found = []
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                found += [child.lineno for alias in child.names if alias.name.split(".")[0] == "playwright"]
            elif isinstance(child, ast.ImportFrom):
                if (child.module or "").split(".")[0] == "playwright":
                    found.append(child.lineno)
        return found

    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "playwright_page_driver"
    )
    inside = set(_playwright_imports(factory))
    assert inside, "the factory must be the place that imports playwright"
    assert set(_playwright_imports(tree)) == inside, (
        "playwright may only be imported lazily inside playwright_page_driver"
    )


def test_a_full_self_check_run_never_imports_playwright():
    probe = (
        "import importlib.util, sys;"
        f"spec = importlib.util.spec_from_file_location('m', r'{MODULE_PATH}');"
        "m = importlib.util.module_from_spec(spec);"
        "sys.modules['m'] = m;"
        "spec.loader.exec_module(m);"
        "code = m.main(['--self-check']);"
        "sys.stderr.write('SELFCHECK=%d PLAYWRIGHT=%s' % (code, 'playwright' in sys.modules))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120, check=False
    )
    assert "SELFCHECK=0" in proc.stderr, proc.stderr[-2000:]
    assert "PLAYWRIGHT=False" in proc.stderr, proc.stderr[-2000:]


def test_annotations_start_the_line_as_bare_prints():
    """A '::warning' routed through a logger never reaches the Actions summary."""

    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def _literal_parts(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            return [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        return []

    found = 0
    for node in ast.walk(tree):
        parts = _literal_parts(node)
        if not any(part.lstrip().startswith("::") or "::warning" in part or "::error" in part for part in parts):
            continue
        # The annotation must be the head of what is printed: GitHub only parses a
        # workflow command at column 0 of the emitted line.
        assert parts[0].startswith("::"), f"annotation must start the emitted string: {parts[0]!r}"
        found += 1
        walker: ast.AST | None = node
        call: ast.Call | None = None
        while walker is not None:
            walker = parents.get(walker)
            if isinstance(walker, ast.Call):
                call = walker
                break
        assert call is not None and isinstance(call.func, ast.Name) and call.func.id == "print", (
            f"annotation {parts[0]!r} must be emitted by a bare print(), not a logger"
        )
        assert any(
            isinstance(kw.arg, str) and kw.arg == "flush" for kw in call.keywords
        ), "stdout is block-buffered when piped in CI; the annotation print must flush"

    assert found >= 3, "the module should still carry its annotation emissions"
    assert "log.warning" not in source and "logger.warning" not in source
