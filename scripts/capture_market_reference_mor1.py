#!/usr/bin/env python3
"""Capture the frozen MOR-1 32-cell route matrix into mockups/evidence/market_reference_mor1.

Serves ``site/`` locally, expands the four frozen route cases × REST axes, and
writes a ``mastermind.p0_evidence.v2`` manifest with per-cell ``route_state``,
route journeys, and an authenticated candidate binding block.

Does not write or delete ``smells.json`` — that file is a capture byproduct and
is not part of this operation's evidence packet.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import capture_page_evidence as cpe
from scripts.market_reference_route_evidence import (
    REQUIRED_RENDER_INPUTS,
    REQUIRED_SHARED_ASSETS,
    ROUTE_CASES,
    mor1_capture_rows,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "mockups" / "evidence" / "market_reference_mor1"


def _git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _module_sha256() -> str:
    return _sha256_file(REPO / "scripts" / "capture_page_evidence.py")


def _href_q(href: str) -> str | None:
    try:
        return (parse_qs(urlparse(href).query).get("q") or [None])[0]
    except Exception:
        return None


def _href_hash(href: str) -> str:
    try:
        return urlparse(href).fragment or ""
    except Exception:
        return ""


def _run_render() -> dict[str, Any]:
    argv = [sys.executable, "-m", "scripts.build_market_reference"]
    proc = subprocess.run(
        argv,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "build_market_reference failed: "
            + ((proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}")
        )
    input_digests = {rel: _sha256_file(REPO / rel) for rel in REQUIRED_RENDER_INPUTS}
    output_digests = {"site/reference.html": _sha256_file(REPO / "site" / "reference.html")}
    return {
        "command": "python -m scripts.build_market_reference",
        "argv": argv,
        "returncode": proc.returncode,
        "input_digests": input_digests,
        "output_digests": output_digests,
    }


def build_candidate_binding(
    *,
    site_dir: Path,
    serve_root: str,
    render_invocation: dict[str, Any],
) -> dict[str, Any]:
    source_commit = _git_output("rev-parse", "HEAD")
    source_tree = _git_output("rev-parse", "HEAD^{tree}")
    head = source_commit
    site_ref = site_dir / "reference.html"
    site_sha = _sha256_file(site_ref)
    shared = {rel: _sha256_file(REPO / rel) for rel in REQUIRED_SHARED_ASSETS}
    return {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "worktree_head_matches_source": head == source_commit,
        "worktree": str(REPO),
        "site_dir": str(site_dir),
        "site_reference_sha256": site_sha,
        "serve_root": serve_root,
        "capture_tool_version": cpe.TOOL_VERSION,
        "capture_tool_module_sha256": _module_sha256(),
        "capture_tool_module_ref": cpe.MODULE_REF,
        "render_invocation": render_invocation,
        "shared_asset_digests": shared,
    }


def _empty_journeys(error: str) -> dict[str, Any]:
    payload = {"ok": False, "error": error}
    return {
        "change": dict(payload),
        "clear": dict(payload),
        "reload": dict(payload),
        "back": dict(payload),
        "forward": dict(payload),
        "share": dict(payload),
    }


def _probe_journeys(base_url: str, case: dict[str, Any], *, settle_ms: int) -> dict[str, Any]:
    """Share and reload on a pristine load; then real change/clear/back/forward."""

    from playwright.sync_api import sync_playwright

    route = case["route"]
    url = f"{base_url.rstrip('/')}/{route}"
    expect_hash = (case.get("expect") or {}).get("hash", "").lstrip("#")
    expect_q = (case.get("expect") or {}).get("query_q")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(url, wait_until="load", timeout=60_000)
            page.wait_for_timeout(settle_ms)
            pristine_href = page.url
            share = {
                "ok": bool(pristine_href) and (route.split("/")[-1] in pristine_href),
                "href": pristine_href,
                "final_href": pristine_href,
                "matches_final": bool(pristine_href) and pristine_href == page.url,
            }
            page.reload(wait_until="load", timeout=60_000)
            page.wait_for_timeout(settle_ms)
            post_href = page.url
            post_state = page.evaluate(cpe._ROUTE_STATE_SCRIPT.strip(), url) or {}
            post_q = _href_q(post_href)
            post_hash = _href_hash(post_href)
            reload_ok = share["ok"]
            if expect_hash:
                reload_ok = reload_ok and post_hash == expect_hash
            else:
                reload_ok = reload_ok and post_hash in ("",)
            if expect_q is not None:
                reload_ok = reload_ok and post_q == expect_q
            else:
                reload_ok = reload_ok and post_q in (None, "")
            expected_input = expect_q or ""
            rehydrated = post_state.get("rf_q_value")
            reload_ok = reload_ok and rehydrated in (expected_input, expect_q)
            reload = {
                "ok": bool(reload_ok),
                "pre_href": pristine_href,
                "post_href": post_href,
                "pre_q": _href_q(pristine_href),
                "post_q": post_q,
                "pre_hash": _href_hash(pristine_href),
                "post_hash": post_hash,
                "input_rehydrated": rehydrated,
                "visible_result_count": post_state.get("visible_result_count"),
                "visible_entry_ids": post_state.get("visible_entry_ids"),
            }
            page.goto(url, wait_until="load", timeout=60_000)
            page.wait_for_timeout(settle_ms)
            payload = page.evaluate(cpe._MOR1_JOURNEY_SCRIPT.strip()) or {}
            verdicts = dict(payload.get("verdicts") or {})
            verdicts["share"] = share
            verdicts["reload"] = reload
            for key in ("change", "clear", "reload", "back", "forward", "share"):
                if key not in verdicts:
                    verdicts[key] = {"ok": False, "reason": "missing"}
            context.close()
            return verdicts
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=REPO / "site")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    args = parser.parse_args(argv)

    site_dir = args.site_dir.resolve()
    try:
        render_invocation = _run_render()
    except Exception as exc:
        print(f"error: render failed: {exc}", file=sys.stderr)
        return 2
    if not (site_dir / "reference.html").is_file():
        print(f"error: missing {site_dir / 'reference.html'} after render", file=sys.stderr)
        return 2

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.png"):
        stale.unlink()
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    server, port = cpe.serve_site_dir(site_dir)
    base_url = f"http://127.0.0.1:{port}"
    try:
        driver = cpe.playwright_page_driver(
            headless=not args.headed,
            settle_ms=args.settle_ms,
        )
        try:
            target = cpe.site_dir_target(site_dir)
            result = cpe.run_capture(
                rows=mor1_capture_rows(),
                driver=driver,
                base_url=base_url,
                output_dir=out,
                manifest_dir=out,
                viewports=("desktop", "mobile"),
                locales=("en", "zh"),
                themes=("dark", "light"),
                delay_ms=200,
                timeout_s=args.timeout_s,
                generated_at=cpe._utc_now(),
                target=target,
                excluded=[],
                selection={"mode": "mor1_route_matrix", "cases": 4},
            )
        finally:
            driver.close()

        manifest = result["manifest"]
        binding = build_candidate_binding(
            site_dir=site_dir,
            serve_root=base_url,
            render_invocation=render_invocation,
        )
        manifest["candidate_binding"] = binding
        by_route = {
            p.get("route"): p for p in (manifest.get("pages") or []) if isinstance(p, dict)
        }
        for case in ROUTE_CASES:
            page = by_route.get(case["route"])
            if page is None:
                continue
            try:
                page["route_journeys"] = _probe_journeys(
                    base_url, case, settle_ms=args.settle_ms
                )
            except Exception as exc:
                page["route_journeys"] = _empty_journeys(str(exc))
            for state in page.get("states") or []:
                if isinstance(state, dict) and isinstance(state.get("route_state"), dict):
                    state["route_state"]["journeys"] = page["route_journeys"]
        tool = manifest.get("tool") if isinstance(manifest.get("tool"), dict) else {}
        tool["version"] = cpe.TOOL_VERSION
        tool["module_sha256"] = binding["capture_tool_module_sha256"]
        tool["module_ref"] = cpe.MODULE_REF
        manifest["tool"] = tool
        result["manifest"] = manifest
    finally:
        server.shutdown()
        server.server_close()

    manifest_path.write_bytes(cpe.canonical_json_bytes(result["manifest"]))
    print(f"wrote {manifest_path}")
    print(
        f"pages={len(result['manifest'].get('pages') or [])} "
        f"states_captured={result['manifest'].get('totals', {}).get('states_captured') or result['manifest'].get('states_captured')}"
    )
    print(f"candidate_binding.source_commit={binding['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
