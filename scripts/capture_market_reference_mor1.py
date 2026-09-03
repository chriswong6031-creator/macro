#!/usr/bin/env python3
"""Capture the frozen MOR-1 32-cell route matrix into mockups/evidence/market_reference_mor1.

Serves ``site/`` locally, expands the four frozen route cases × REST axes, and
writes a ``mastermind.p0_evidence.v2`` manifest with per-cell ``route_state``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts import capture_page_evidence as cpe
from scripts.market_reference_route_evidence import mor1_capture_rows

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "mockups" / "evidence" / "market_reference_mor1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=REPO / "site")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    args = parser.parse_args(argv)

    site_dir = args.site_dir.resolve()
    if not (site_dir / "reference.html").is_file():
        print(f"error: missing {site_dir / 'reference.html'} — build first", file=sys.stderr)
        return 2

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Drop prior PNGs/manifest so content-addressed names cannot leave orphans.
    for stale in out.glob("*.png"):
        stale.unlink()
    for name in ("manifest.json", "smells.json", "smells.md"):
        path = out / name
        if path.exists():
            path.unlink()

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
    finally:
        server.shutdown()
        server.server_close()

    manifest_path = out / "manifest.json"
    manifest_path.write_bytes(cpe.canonical_json_bytes(result["manifest"]))
    smells_path = out / "smells.json"
    smells_path.write_bytes(cpe.canonical_json_bytes(result["smells"]))
    print(f"wrote {manifest_path}")
    print(f"pages={len(result['manifest'].get('pages') or [])} "
          f"states_captured={result['manifest'].get('states_captured')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
