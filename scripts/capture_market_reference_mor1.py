#!/usr/bin/env python3
"""Capture the frozen MOR-1 32-cell route matrix into mockups/evidence/market_reference_mor1.

Serves ``site/`` locally, expands the four frozen route cases × REST axes, and
writes a ``mastermind.p0_evidence.v2`` manifest with per-cell ``route_state``,
per-cell console/response receipts, one axes-bound ``route_journey`` per route
page, and an authenticated candidate binding block.

Two identity rules this module exists to hold:

* **Capture from a clean immutable subject.** It refuses to run when any TRACKED
  path outside its own evidence directory is modified, so every digest it
  records is a digest of a committed blob rather than of whatever happened to be
  on disk. Its own outputs are excluded from that receipt — requiring them
  unchanged while producing them is unsatisfiable — and the verifier enforces
  the other half: the evidence commit may change no owned non-evidence path.
* **A journey belongs to the cell that ran it.** Exactly one journey is executed
  per route page, in one explicitly recorded viewport/locale/theme/access, and
  it is stored once at page level. It is never copied into the 32 per-state
  records, which would claim behavior those cells never executed.

Does not write or delete ``smells.json`` — that file is a capture byproduct and
is not part of this operation's evidence packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Entry-script pin: unconditional, top level, before the first repo import, so a
# bare `python3 scripts/capture_market_reference_mor1.py` cannot resolve a repo
# import to a foreign tree.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from scripts import capture_page_evidence as cpe  # noqa: E402
from scripts.market_reference_route_evidence import (  # noqa: E402
    EVIDENCE_DIR_REL,
    REQUIRED_RENDER_INPUTS,
    ROUTE_CASES,
    derive_local_assets,
    mor1_capture_rows,
    resolve_probe_queries,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "mockups" / "evidence" / "market_reference_mor1"

# The single cell the page-level journey is executed in and bound to.
JOURNEY_AXES = {
    "viewport": "desktop",
    "locale": "en",
    "theme": "dark",
    "access": "anonymous",
    "force_state": None,
}


def _git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def _status_lines() -> list[str]:
    """Raw porcelain lines — NOT run through ``_git_output``.

    ``_git_output`` strips the whole stdout, which eats the leading status
    space of the FIRST line only (`` D path`` -> ``D path``). That silently
    shifted one path by a character and made exactly one entry escape the
    evidence-directory filter.
    """

    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in (proc.stdout or "").split("\n") if line.strip()]


def _status_path(line: str) -> str:
    path = line[3:] if len(line) > 3 else ""
    if " -> " in path:  # rename/copy
        path = path.split(" -> ", 1)[1]
    return path.strip().strip('"')


def _tracked_status(*, include_evidence: bool = False) -> list[str]:
    """Porcelain lines for TRACKED paths, excluding the evidence directory.

    Two exclusions, both deliberate:

    * ``smells.json`` is a preserved untracked byproduct (Sol
      1788478472.222509), so untracked entries never make the tree dirty.
    * The evidence directory is this tool's OUTPUT. The clean-tree receipt is a
      statement about the SUBJECT — source, tool, product, tests — because
      requiring the outputs to be unchanged while producing them is not a
      condition anything could satisfy. The verifier enforces the other half:
      the evidence commit may change no owned non-evidence path.
    """

    lines = []
    for line in _status_lines():
        if not line or line.startswith("??"):
            continue
        if not include_evidence and _status_path(line).startswith(EVIDENCE_DIR_REL + "/"):
            continue
        lines.append(line)
    return lines


def _evidence_status() -> list[str]:
    return [
        line
        for line in _status_lines()
        if _status_path(line).startswith(EVIDENCE_DIR_REL + "/")
    ]


def _untracked_status() -> list[str]:
    return [line for line in _status_lines() if line.startswith("??")]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _module_sha256() -> str:
    return _sha256_file(REPO / "scripts" / "capture_page_evidence.py")


def _run_render() -> dict[str, Any]:
    """Run the real builder and receipt it.

    ``site/reference.html`` is NOT bit-reproducible: the page stamps its own
    build time ("Updated <UTC>"), so two renders minutes apart differ by one
    line. That is why render and capture are separate phases — the rendered
    artifact is committed into the subject, and the capture then serves exactly
    those committed bytes instead of re-rendering underneath itself and
    dirtying the tree it just claimed was clean.
    """

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
        "cwd": str(REPO.resolve()),
        "returncode": proc.returncode,
        "input_digests": input_digests,
        "output_digests": output_digests,
        "bit_reproducible": False,
        "not_reproducible_reason": "the page stamps its own build time (Updated <UTC>)",
    }


def _load_render_receipt(path: Path) -> dict[str, Any]:
    """Reuse the receipt of the render whose output is the committed subject.

    Trust is bounded: the verifier independently re-derives every declared
    input/output digest from subject-commit blobs, so a receipt can only claim
    what the committed tree already proves.
    """

    receipt = json.loads(path.read_text(encoding="utf-8"))
    declared = (receipt.get("output_digests") or {}).get("site/reference.html")
    actual = _sha256_file(REPO / "site" / "reference.html")
    if declared != actual:
        raise RuntimeError(
            "render receipt does not describe the artifact on disk: "
            f"receipt {str(declared)[:16]}… != site/reference.html {actual[:16]}…"
        )
    if receipt.get("returncode") != 0:
        raise RuntimeError(f"render receipt returncode is {receipt.get('returncode')!r}, not 0")
    return receipt


def build_candidate_binding(
    *,
    site_dir: Path,
    serve_root: str,
    render_invocation: dict[str, Any],
) -> dict[str, Any]:
    source_commit = _git_output("rev-parse", "HEAD")
    source_tree = _git_output("rev-parse", "HEAD^{tree}")
    tracked = _tracked_status()
    site_ref = site_dir / "reference.html"
    site_sha = _sha256_file(site_ref)
    # The asset receipt is DERIVED from the page that was actually served, so an
    # asset the page loads can never be missing from the graph.
    html = site_ref.read_text(encoding="utf-8", errors="replace")
    local_assets = {}
    for rel in derive_local_assets(html):
        path = REPO / rel
        if path.is_file():
            local_assets[rel] = _sha256_file(path)
        else:
            local_assets[rel] = ""
    return {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "worktree": str(REPO),
        "worktree_clean": not tracked,
        "worktree_status_tracked": tracked,
        "worktree_status_untracked": _untracked_status(),
        "evidence_status_tracked": _evidence_status(),
        "site_dir": str(site_dir),
        "site_reference_sha256": site_sha,
        "serve_root": serve_root,
        "capture_tool_version": cpe.TOOL_VERSION,
        "capture_tool_module_sha256": _module_sha256(),
        "capture_tool_module_ref": cpe.MODULE_REF,
        "verifier_module_sha256": _sha256_file(
            REPO / "scripts" / "market_reference_route_evidence.py"
        ),
        "render_invocation": render_invocation,
        "local_asset_digests": local_assets,
        "local_asset_source": "derived from rendered site/reference.html",
    }


def _parsed(href: str) -> dict[str, Any]:
    parsed = urlparse(href or "")
    return {
        "pathname": parsed.path or "",
        "search": f"?{parsed.query}" if parsed.query else "",
        "hash": f"#{parsed.fragment}" if parsed.fragment else "",
        "url_q": (parse_qs(parsed.query).get("q") or [None])[0],
    }


def _attach_listeners(page: Any, console: list[dict[str, Any]], failed: list[dict[str, Any]]) -> None:
    """Journey-scoped failure capture.

    Without these a change/clear/back/forward path could throw, or take a
    required 4xx/5xx, while its final DOM fields still looked correct.
    """

    def _on_console(msg: Any) -> None:
        if msg.type != "error":
            return
        try:
            source_url = (msg.location or {}).get("url") or None
        except Exception:
            source_url = None
        console.append({"text": msg.text, "source_url": source_url})

    def _on_response(response: Any) -> None:
        try:
            if response.status >= 400:
                failed.append({"url": response.url, "status": int(response.status)})
        except Exception:
            pass

    page.on("console", _on_console)
    page.on("pageerror", lambda err: console.append({"text": f"pageerror: {err}", "source_url": None}))
    page.on("response", _on_response)


def _probe_journey(
    browser: Any,
    base_url: str,
    case: dict[str, Any],
    *,
    settle_ms: int,
    probes: dict[str, Any],
) -> dict[str, Any]:
    """One journey, in one explicitly bound cell, with its own failure receipts."""

    route = case["route"]
    url = f"{base_url.rstrip('/')}/{route}"
    width, height = cpe.VIEWPORTS[JOURNEY_AXES["viewport"]]
    state = {"theme": JOURNEY_AXES["theme"], "locale": JOURNEY_AXES["locale"]}
    console: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    context = browser.new_context(
        viewport={"width": width, "height": height},
        user_agent=cpe.USER_AGENT,
        locale="zh-CN" if JOURNEY_AXES["locale"] == "zh" else "en-US",
        color_scheme=JOURNEY_AXES["theme"],
        device_scale_factor=1,
    )
    context.add_init_script(f"({cpe._STATE_SEED_SCRIPT.strip()})({json.dumps(state)})")
    try:
        page = context.new_page()
        _attach_listeners(page, console, failed)
        page.goto(url, wait_until="load", timeout=60_000)
        page.wait_for_timeout(settle_ms)
        applied = page.evaluate(cpe._APPLY_STATE_SCRIPT.strip(), state) or {}
        page.wait_for_timeout(settle_ms)

        # --- reload, on the pristine load, before any mutation --------------
        pristine_href = page.url
        page.reload(wait_until="load", timeout=60_000)
        page.wait_for_timeout(settle_ms)
        reload_state = page.evaluate(cpe._ROUTE_STATE_SCRIPT.strip(), url) or {}
        reload_step = dict(_parsed(page.url))
        reload_step.update(
            {
                "step": "reload",
                "href": page.url,
                "pre_href": pristine_href,
                "input": reload_state.get("rf_q_value"),
                "visible_result_count": reload_state.get("visible_result_count"),
                "visible_entry_ids": reload_state.get("visible_entry_ids"),
                "count_label_numerator": reload_state.get("count_label_numerator"),
                "count_label_denominator": reload_state.get("count_label_denominator"),
            }
        )

        # --- change / empty / clear / back / forward ------------------------
        page.goto(url, wait_until="load", timeout=60_000)
        page.wait_for_timeout(settle_ms)
        payload = page.evaluate(
            cpe._MOR1_JOURNEY_SCRIPT.strip(),
            {
                "changeQuery": probes["change_query"],
                "forwardQuery": probes["forward_query"],
                "emptyQuery": probes["empty_query"],
            },
        ) or {}
        steps = dict(payload.get("steps") or {})
        steps["reload"] = reload_step

        # --- share: REOPEN the captured href in a clean context -------------
        share_href = str(steps.get("initial", {}).get("href") or pristine_href)
        steps["share"] = _share_round_trip(
            browser,
            share_href,
            settle_ms=settle_ms,
            state=state,
            width=width,
            height=height,
        )
        return {
            "axes": {
                **JOURNEY_AXES,
                "viewport_width": width,
                "viewport_height": height,
            },
            "applied": {
                "locale": applied.get("locale"),
                "theme": applied.get("theme"),
                "viewport_width": width,
                "viewport_height": height,
            },
            "probes": {
                "change_query": probes["change_query"],
                "forward_query": probes["forward_query"],
                "empty_query": probes["empty_query"],
            },
            "console_errors": console,
            "failed_responses": failed,
            "steps": steps,
        }
    finally:
        context.close()


def _share_round_trip(
    browser: Any,
    href: str,
    *,
    settle_ms: int,
    state: dict[str, Any],
    width: int,
    height: int,
) -> dict[str, Any]:
    """Open the share target in a clean context and read what it actually renders.

    ``href == page.url`` proves only that a string equals itself. A page whose
    route cannot rehydrate in a fresh browser used to pass this step.
    """

    console: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    context = browser.new_context(
        viewport={"width": width, "height": height},
        user_agent=cpe.USER_AGENT,
        locale="zh-CN" if state["locale"] == "zh" else "en-US",
        color_scheme=state["theme"],
        device_scale_factor=1,
    )
    context.add_init_script(f"({cpe._STATE_SEED_SCRIPT.strip()})({json.dumps(state)})")
    try:
        page = context.new_page()
        _attach_listeners(page, console, failed)
        page.goto(href, wait_until="load", timeout=60_000)
        page.wait_for_timeout(settle_ms)
        page.evaluate(cpe._APPLY_STATE_SCRIPT.strip(), state)
        page.wait_for_timeout(settle_ms)
        page.evaluate(cpe._REFOCUS_TARGET_SCRIPT.strip())
        page.wait_for_timeout(120)
        rs = page.evaluate(cpe._ROUTE_STATE_SCRIPT.strip(), href) or {}
        final_href = page.url
        reopened = dict(_parsed(final_href))
        reopened.update(
            {
                "final_href": final_href,
                "input": rs.get("rf_q_value"),
                "visible_result_count": rs.get("visible_result_count"),
                "visible_entry_ids": rs.get("visible_entry_ids"),
                "count_label_numerator": rs.get("count_label_numerator"),
                "count_label_denominator": rs.get("count_label_denominator"),
                "selected_id": rs.get("selected_id"),
                "miss_visible": rs.get("miss_visible"),
                "focused_element_id": rs.get("focused_element_id"),
                "focused_visible": rs.get("focused_visible"),
                "target_below_fixed_ui": rs.get("target_below_fixed_ui"),
                "console_errors": console,
                "failed_responses": failed,
            }
        )
        # ``final_href`` is where the browser SETTLED after reopening the shared
        # URL, so matches_final is a round-trip result. The retired form set
        # final_href = href and compared a string to itself.
        def _key(u: str) -> tuple[str, str | None, str]:
            p = _parsed(u)
            return (p["pathname"], p["url_q"], p["hash"])

        return {
            "step": "share",
            "href": href,
            "final_href": final_href,
            "matches_final": _key(href) == _key(final_href),
            "reopened": reopened,
        }
    finally:
        context.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=REPO / "site")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="record the dirty state instead of refusing (the packet will be RED)",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="phase 1: render site/reference.html and write its receipt, then stop "
        "(the rendered artifact is committed into the subject)",
    )
    parser.add_argument(
        "--receipt-out",
        type=Path,
        default=None,
        help="where --render-only writes the render receipt",
    )
    parser.add_argument(
        "--render-receipt",
        type=Path,
        default=None,
        help="phase 2: reuse this receipt and serve the committed bytes instead of "
        "re-rendering underneath the subject commit",
    )
    args = parser.parse_args(argv)

    if args.render_only:
        if args.receipt_out is None:
            print("error: --render-only requires --receipt-out", file=sys.stderr)
            return 2
        try:
            receipt = _run_render()
        except Exception as exc:
            print(f"error: render failed: {exc}", file=sys.stderr)
            return 2
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        print(f"rendered; receipt -> {args.receipt_out}")
        print(f"site/reference.html sha256={receipt['output_digests']['site/reference.html']}")
        print("commit site/reference.html into the subject, then capture with --render-receipt")
        return 0

    tracked = _tracked_status()
    if tracked and not args.allow_dirty:
        print(
            "error: refusing to capture from a dirty worktree — commit the subject first.\n"
            + "\n".join(f"  {line}" for line in tracked),
            file=sys.stderr,
        )
        return 2

    site_dir = args.site_dir.resolve()
    try:
        if args.render_receipt is not None:
            render_invocation = _load_render_receipt(args.render_receipt)
        else:
            render_invocation = _run_render()
    except Exception as exc:
        print(f"error: render receipt unusable: {exc}", file=sys.stderr)
        return 2
    if not (site_dir / "reference.html").is_file():
        print(f"error: missing {site_dir / 'reference.html'}", file=sys.stderr)
        return 2
    # Capture must not dirty the subject it is binding to: if the tree moved,
    # the committed subject no longer describes the bytes being served.
    post_render_tracked = _tracked_status()
    if post_render_tracked and not args.allow_dirty:
        print(
            "error: tracked files changed before capture; the subject commit does not "
            "describe the served bytes.\n"
            + "\n".join(f"  {line}" for line in post_render_tracked),
            file=sys.stderr,
        )
        return 2

    probes = resolve_probe_queries(REPO)

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

        from playwright.sync_api import sync_playwright

        by_route = {
            p.get("route"): p for p in (manifest.get("pages") or []) if isinstance(p, dict)
        }
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            try:
                for case in ROUTE_CASES:
                    page = by_route.get(case["route"])
                    if page is None:
                        continue
                    page["route_journey"] = _probe_journey(
                        browser,
                        base_url,
                        case,
                        settle_ms=args.settle_ms,
                        probes=probes,
                    )
                    # Deliberately NOT copied into page["states"][*]["route_state"]:
                    # one default-context interaction is not 32-cell behavior.
                    page.pop("route_journeys", None)
                    for state in page.get("states") or []:
                        if isinstance(state, dict) and isinstance(state.get("route_state"), dict):
                            state["route_state"].pop("journeys", None)
            finally:
                browser.close()

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
    print(f"manifest sha256={hashlib.sha256(manifest_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
