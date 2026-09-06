"""Local evidence: real owner -> existing publisher -> reader -> page -> browser.

Run with --out pointing to a NEW evidence directory, never site/ or data/.
Only growth uses a fully present real owner in a sparse checkout. This probe does
not claim a full healthy suite, a deployed artifact, or production auth proof.
"""
from __future__ import annotations
import argparse
import functools
import hashlib
import json
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.market_os.macro_workspaces import build, contract, growth
from scripts import build_macro_suite_pages as pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    target = parser.parse_args().out.resolve()
    for forbidden in (ROOT / "site", ROOT / "data"):
        if target == forbidden or forbidden in target.parents:
            raise ValueError("Evidence output must not write product site or data")
    target.mkdir(parents=True, exist_ok=False)
    stamp = datetime.now(timezone.utc).isoformat()
    owner = ROOT / "data/regime/latest.json"
    raw = owner.read_bytes()
    assert raw == subprocess.check_output(["git", "show", "HEAD:data/regime/latest.json"], cwd=ROOT)
    regime = json.loads(raw)
    tiers = regime["business_cycle"]["tiers"]
    site = target / "site"
    data_root = site / "macrodata"
    receipts = build.build_all(out_root=data_root, regime_latest_path=owner,
                               built_at=stamp, code_version="local-period-fidelity-candidate")
    page = next(p for p in pages.SUITE_PAGES if p.workspace_id == "growth_real_economy")
    snapshot, _ = pages.read_workspace(data_root, page)
    contract.validate(snapshot)
    periods = {name: tier.get("asof") for name, tier in tiers.items()}
    expected = {}
    for metric in snapshot["metrics"]["items"]:
        if metric["definition_id"].startswith("business_cycle.tiers."):
            tier = metric["definition_id"].split(".")[2]
            assert metric["reference_period"] == periods[tier]
            assert metric["observed_at"] is None
            assert metric["calculation_as_of"] == regime["asof"]
            expected[metric["definition_id"]] = periods[tier]
    assert len(expected) == 9
    destination, ok = pages.build_page(ROOT, page, data_root=data_root,
                                      out_dir=site, env=pages._environment(ROOT), page_built_at=stamp)
    assert ok, "The actual page consumer refused the real growth snapshot"
    # Serve the existing public static assets; no application/auth override.
    for asset in (ROOT / "templates").iterdir():
        if asset.is_file() and asset.suffix in (".css", ".js"):
            shutil.copyfile(asset, site / asset.name)
    fonts = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD", "site/fonts"], cwd=ROOT, text=True)
    for relative in fonts.splitlines():
        path = site / Path(relative).relative_to("site")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=ROOT))

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {
        "classification": "LOCAL_REAL_GROWTH_OWNER_NOT_PRODUCTION",
        "built_at": stamp, "parent_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "owner_sha256": hashlib.sha256(raw).hexdigest(),
        "composer_sha256": hashlib.sha256((ROOT / "engine/market_os/macro_workspaces/growth.py").read_bytes()).hexdigest(),
        "snapshot_digest": snapshot["generation"]["content_sha256"],
        "html_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "source_periods": periods, "cases": [],
    }
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            for width in (1440, 390):
                for theme, lang in (("dark", "en"), ("light", "en"), ("dark", "zh"), ("light", "zh")):
                    context = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                    tab = context.new_page()
                    errors = []
                    tab.on("pageerror", lambda error: errors.append(str(error)))
                    tab.goto(f"http://127.0.0.1:{server.server_port}/{page.output}", wait_until="load")
                    tab.evaluate("([t,l])=>{document.documentElement.dataset.theme=t;document.documentElement.dataset.lang=l;document.documentElement.lang=l;}", [theme, lang])
                    checked = {}
                    for definition, expected_period in expected.items():
                        card = tab.locator("article.mq-metric").filter(has_text=definition)
                        assert card.count() == 1, definition
                        assert card.locator(".mq-metric-meta time").inner_text() == expected_period
                        card.locator(".mq-metric-clocks > summary").click()
                        observed = card.locator(".mq-clock").filter(has=tab.locator(".mq-clock-name", has_text="Observed"))
                        calculation = card.locator(".mq-clock").filter(has=tab.locator(".mq-clock-name", has_text="Calculation as-of"))
                        assert observed.locator("dd time").count() == 0
                        assert observed.locator("dd .mq-dash").count() == 1
                        assert calculation.locator("dd time").inner_text() == regime["asof"]
                        checked[definition] = expected_period
                        if definition == "business_cycle.tiers.coincident.diffusion":
                            card.screenshot(path=str(target / f"coincident-{width}-{theme}-{lang}.png"))
                    overflow = tab.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
                    assert not overflow and not errors, (overflow, errors)
                    report["cases"].append({"width": width, "theme": theme, "language": lang,
                                             "verified_periods": checked, "overflow": overflow, "page_errors": errors})
                    context.close()
            browser.close()
        report["status"] = "PASS"
        return 0
    finally:
        server.shutdown()
        (target / "receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({"status": report.get("status", "INCOMPLETE"), "cases": len(report["cases"]),
                          "owner_sha256": report["owner_sha256"], "receipt": str(target / "receipt.json")}))


if __name__ == "__main__":
    raise SystemExit(main())
