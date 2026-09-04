#!/usr/bin/env python3
"""Capture reproducible F02-X1 interaction and degraded-state browser evidence.

The canonical eight-cell rest matrix belongs to ``capture_page_evidence.py``.
This companion drives states that a rest capture cannot reach. Interaction
captures use the committed site and real on-demand shards. Degraded captures
use the real page code with a labelled scratch projection; they demonstrate
presentation behavior and never assert that an official-source outage occurred.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


DATA_NAME = "sanctions-geography-data.json"
SHARD_PATH_TOKEN = "/sanctions-geography-entries/"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serve a bounded scratch root without polluting the evidence log."""

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class ReusableThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def serve(root: Path) -> tuple[ReusableThreadingServer, int]:
    handler = functools.partial(QuietHandler, directory=str(root))
    server = ReusableThreadingServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


def scratch(site: Path, mutate: Callable[[dict[str, Any]], None] | None = None) -> Path:
    """Symlink the real site, optionally replacing only the summary projection."""

    root = Path(tempfile.mkdtemp(prefix="f02x1-site-"))
    for entry in site.iterdir():
        if entry.name == DATA_NAME and mutate is not None:
            continue
        os.symlink(entry, root / entry.name)
    if mutate is not None:
        projection = json.loads((site / DATA_NAME).read_text(encoding="utf-8"))
        mutate(projection)
        projection["_fixture_note"] = (
            "SYNTHETIC FIXTURE - source_state/freshness overridden locally to "
            "observe degraded presentation. This is not a real source outage "
            "and is never written to the committed artifact."
        )
        (root / DATA_NAME).write_text(
            json.dumps(projection, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    return root


def capture(*, repo: Path, output: Path) -> None:
    """Run the browser matrix and replace its machine observation receipt."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "playwright is required; use the same isolated browser environment "
            "as scripts/capture_page_evidence.py"
        ) from exc

    site = repo / "site"
    if not (site / DATA_NAME).is_file():
        raise SystemExit(f"missing committed projection: {site / DATA_NAME}")
    projection = json.loads((site / DATA_NAME).read_text(encoding="utf-8"))

    def file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    artifact_receipt = {
        "projection_id": projection.get("projection_id"),
        "source_identity": projection.get("source_identity"),
        "data_sha256": file_sha256(site / DATA_NAME),
        "page_sha256": file_sha256(site / "sanctions-geography.html"),
        "css_sha256": file_sha256(site / "sanctions-geography.css"),
        "js_sha256": file_sha256(site / "sanctions-geography.js"),
        "driver_sha256": file_sha256(Path(__file__).resolve()),
    }
    output.mkdir(parents=True, exist_ok=True)
    observations: list[dict[str, Any]] = []

    def shot(page: Any, name: str, theme: str, locale: str, checks: dict[str, Any]) -> None:
        path = output / f"{name}-{theme}-{locale}.png"
        page.screenshot(path=str(path), full_page=True)
        observations.append(
            {
                "state": name,
                "theme": theme,
                "locale": locale,
                "file": path.name,
                "observations": checks,
            }
        )
        print(f"{path.name}: {json.dumps(checks, ensure_ascii=False, sort_keys=True)}")

    def open_page(browser: Any, port: int, theme: str, locale: str) -> tuple[Any, Any]:
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(
            "localStorage.setItem('theme', %s); localStorage.setItem('lang', %s);"
            % (json.dumps(theme), json.dumps(locale))
        )
        page = context.new_page()
        page.goto(
            f"http://127.0.0.1:{port}/sanctions-geography.html",
            wait_until="networkidle",
        )
        page.wait_for_timeout(500)
        return context, page

    scratch_roots: list[Path] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            # Interaction states use the real committed projection and shards.
            real_root = scratch(site)
            scratch_roots.append(real_root)
            server, port = serve(real_root)
            try:
                for theme in ("dark", "light"):
                    context, page = open_page(browser, port, theme, "en")
                    shard_requests: list[str] = []
                    page.on(
                        "request",
                        lambda request: shard_requests.append(request.url)
                        if SHARD_PATH_TOKEN in request.url
                        else None,
                    )
                    # The listener is intentionally installed after network-idle:
                    # the initial page load must not have fetched a shard, which is
                    # also checked through Resource Timing below.
                    initial_resources = page.evaluate(
                        "performance.getEntriesByType('resource')"
                        ".filter(e => e.name.includes('/sanctions-geography-entries/')).length"
                    )

                    row = page.locator("[data-sg-tbody] tr[data-geo-id]").first
                    boundary = row.locator("td").first.inner_text()
                    row.focus()
                    page.keyboard.press("Enter")
                    page.wait_for_function(
                        "document.querySelectorAll('[data-sg-entries] .sg-entry').length > 0 || "
                        "document.querySelector('[data-sg-entries] code')"
                    )
                    page.wait_for_timeout(150)
                    selected_before = page.locator(".sg-geo.is-on").count()
                    selected_path = page.locator(".sg-geo.is-on").first
                    page.evaluate(
                        "document.documentElement.setAttribute('data-lang','zh');"
                        "document.dispatchEvent(new Event('langchange'))"
                    )
                    zh_name = selected_path.get_attribute("aria-label") or ""
                    page.evaluate(
                        "document.documentElement.setAttribute('data-lang','en');"
                        "document.dispatchEvent(new Event('langchange'))"
                    )
                    shot(
                        page,
                        "selected-boundary",
                        theme,
                        "en",
                        {
                            "boundary": boundary,
                            "row_focusable": row.get_attribute("tabindex") == "0",
                            "row_selected": "is-on" in (row.get_attribute("class") or ""),
                            "map_path_selected": selected_before,
                            "entry_cards": page.locator("[data-sg-entries] .sg-entry").count(),
                            "initial_shard_requests": int(initial_resources),
                            "selection_shard_requests": len(shard_requests),
                            "selected_shard_path": shard_requests[0].split("/")[-1]
                            if shard_requests
                            else None,
                            "zh_map_name_applied": "条名单记录" in zh_name,
                            "identityless_paths": page.locator(".sg-geo.is-identityless").count(),
                            "identityless_paths_with_zero_count": page.locator(
                                ".sg-geo.is-identityless[data-count='0']"
                            ).count(),
                        },
                    )

                    # Pick the first program that excludes the active boundary.
                    # The observed value is the transition count (1 -> 0), not
                    # merely the final count, so the receipt proves the clear path.
                    program = page.locator("[data-sg-program]")
                    selected_after = selected_before
                    chosen_program = ""
                    for candidate in program.locator("option").evaluate_all(
                        "opts => opts.map(o => o.value).filter(Boolean)"
                    ):
                        page.select_option("[data-sg-program]", candidate)
                        page.wait_for_timeout(80)
                        selected_after = page.locator(".sg-geo.is-on").count()
                        if selected_after == 0:
                            chosen_program = candidate
                            break
                    dimmed = page.locator(".sg-geo.is-off")
                    keyboard_reachable = page.eval_on_selector_all(
                        ".sg-geo.is-off",
                        "els => els.filter(e => e.getAttribute('tabindex') !== '-1').length",
                    )
                    aria_wrong = page.eval_on_selector_all(
                        ".sg-geo.is-off",
                        "els => els.filter(e => e.getAttribute('aria-disabled') !== 'true').length",
                    )
                    eligible_focusable = page.eval_on_selector_all(
                        ".sg-geo.is-pick:not(.is-off)",
                        "els => els.filter(e => e.getAttribute('tabindex') === '0').length",
                    )
                    shot(
                        page,
                        "filtered-map-sync",
                        theme,
                        "en",
                        {
                            "program": chosen_program,
                            "rows": page.locator("[data-sg-tbody] tr[data-geo-id]").count(),
                            "boundaries_dimmed": dimmed.count(),
                            "boundaries_lit": page.locator(".sg-geo:not(.is-off)").count(),
                            "selection_cleared": selected_before - selected_after,
                            "dimmed_still_keyboard_reachable": keyboard_reachable,
                            "dimmed_missing_aria_disabled": aria_wrong,
                            "eligible_still_focusable": eligible_focusable,
                            "shard_requests_after_filter": len(shard_requests),
                        },
                    )
                    page.select_option("[data-sg-program]", "")

                    page.fill("[data-sg-search]", "zzzz-no-such-boundary")
                    page.wait_for_timeout(100)
                    shot(
                        page,
                        "no-results",
                        theme,
                        "en",
                        {
                            "rows": page.locator("[data-sg-tbody] tr[data-geo-id]").count(),
                            "empty_shown": page.locator("[data-sg-tbody] .sg-empty").count(),
                            "cause_stated": page.locator("[data-sg-tbody] .sg-empty-why").count(),
                            "state_code": page.locator("[data-sg-tbody] code").first.inner_text(),
                        },
                    )
                    page.fill("[data-sg-search]", "")
                    page.select_option("[data-sg-view]", "unresolved")
                    page.wait_for_timeout(100)
                    shot(
                        page,
                        "unresolved-register",
                        theme,
                        "en",
                        {
                            "rows": page.locator("[data-sg-tbody] tr").count(),
                            "program_filter_disabled": page.locator(
                                "[data-sg-program]"
                            ).is_disabled(),
                            "type_filter_disabled": page.locator("[data-sg-type]").is_disabled(),
                            "header": page.locator("[data-sg-thead] th").first.inner_text(),
                        },
                    )
                    context.close()
            finally:
                server.shutdown()
                server.server_close()

            def past_deadline(projection: dict[str, Any]) -> None:
                projection["source_state"] = "CURRENT"
                projection.setdefault("freshness", {})["stale_after"] = "2026-01-01T00:00:00Z"

            fixtures: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
                ("stale-derived", past_deadline, "SOURCE_STALE"),
                (
                    "unavailable",
                    lambda projection: projection.update({"source_state": "SOURCE_UNAVAILABLE"}),
                    "SOURCE_UNAVAILABLE",
                ),
                (
                    "parser-shape-changed",
                    lambda projection: projection.update({"source_state": "PARSER_SHAPE_CHANGED"}),
                    "PARSER_SHAPE_CHANGED",
                ),
            ]
            for name, mutate, expected_state in fixtures:
                fixture_root = scratch(site, mutate)
                scratch_roots.append(fixture_root)
                server, port = serve(fixture_root)
                try:
                    for theme, locale in (("dark", "en"), ("light", "en"), ("dark", "zh")):
                        context, page = open_page(browser, port, theme, locale)
                        banner = page.locator("[data-sg-banner] .sg-degraded")
                        text = banner.inner_text() if banner.count() else ""
                        shot(
                            page,
                            name,
                            theme,
                            locale,
                            {
                                "banner_shown": banner.count(),
                                "state_code_visible": expected_state in text,
                                "role": banner.get_attribute("role") if banner.count() else None,
                                "counts_still_readable": page.locator(".sg-fig-v").first.inner_text(),
                                "fixture": "SYNTHETIC - source_state/freshness overridden locally",
                            },
                        )
                        context.close()
                finally:
                    server.shutdown()
                    server.server_close()
        finally:
            browser.close()
            for root in scratch_roots:
                shutil.rmtree(root, ignore_errors=True)

    (output / "observations.json").write_text(
        json.dumps(
            {
                "schema": "f02x1.state_evidence.v2",
                "driver": "scripts/capture_sanctions_geography_states.py",
                "artifacts": artifact_receipt,
                "note": (
                    "Interaction states use the real committed artifact and shards. "
                    "Degraded states use the real page code with a labelled synthetic "
                    "projection fixture; no committed artifact is modified and no "
                    "source outage is asserted."
                ),
                "viewport": {"width": 1440, "height": 900},
                "captures": observations,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(observations)} captures and {output / 'observations.json'}")


def main() -> int:
    repo_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=repo_default)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = (args.output or repo / "mockups/evidence/sanctions-geography/states").resolve()
    capture(repo=repo, output=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
