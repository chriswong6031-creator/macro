#!/usr/bin/env python3
"""Build + validate + atomically publish Macro & Monetary workspace snapshots.

R1A publishes exactly one vertical, the US Liquidity Regime Monitor:

    site/macrodata/workspaces/liquidity_regime/US/latest.json
    site/macrodata/workspaces/manifest.json

The snapshot is composed from the owner artifact ``data/regime/latest.json``,
sealed with a deterministic content digest, and validated against the closed
``mastermind.macro_workspace_snapshot.v1`` schema before anything is written.
Nothing here mutates an owner path; the projection has no rank/gate/size/trade
authority.

Usage:
    python3 scripts/build_macro_workspaces.py
    python3 scripts/build_macro_workspaces.py --regime-latest data/regime/latest.json
    python3 scripts/build_macro_workspaces.py --out-root /tmp/out --no-write --print
    python3 scripts/build_macro_workspaces.py --prior-snapshot <prev latest.json>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import build as _build  # noqa: E402


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        return out.stdout.strip() or None
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regime-latest", default=str(_build.DEFAULT_REGIME_LATEST),
                        help="owner artifact path (default data/regime/latest.json)")
    parser.add_argument("--out-root", default=str(_build.DEFAULT_OUT_ROOT),
                        help="publication root (default site/macrodata)")
    parser.add_argument("--built-at", default=None, help="generation clock (ISO-8601 UTC); default now")
    parser.add_argument("--prior-snapshot", default=None,
                        help="prior accepted latest.json for changes/1M-vector comparison")
    parser.add_argument("--code-version", default=None, help="override git sha stamp")
    parser.add_argument("--no-write", action="store_true", help="compose+validate only; do not publish")
    parser.add_argument("--print", dest="do_print", action="store_true",
                        help="print the sealed snapshot to stdout")
    args = parser.parse_args(argv)

    built_at = args.built_at or _utc_now_iso()
    code_version = args.code_version or _git_sha()

    receipt = _build.build_liquidity_regime(
        regime_latest_path=args.regime_latest,
        out_root=args.out_root,
        built_at=built_at,
        prior_snapshot_path=args.prior_snapshot,
        code_version=code_version,
        write=not args.no_write,
    )

    snap = receipt["snapshot"]
    summary = {
        "workspace": "liquidity_regime/US",
        "built_at": built_at,
        "code_version": code_version,
        "generation_id": snap["generation"]["generation_id"],
        "content_sha256": receipt["digest"],
        "bytes": receipt["bytes"],
        "headline_state": snap["headline"]["state_id"],
        "state_label": snap["headline"]["state_label"]["en"],
        "funding_pressure_x": snap["headline"]["quadrant"]["x"],
        "balance_sheet_support_y": snap["headline"]["quadrant"]["y"],
        "one_month_vector": snap["headline"]["one_month_vector"],
        "availability_state": snap["availability"]["state"],
        "contradiction": snap["availability"]["contradiction"]["present"],
        "written": receipt["paths"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.do_print:
        print(json.dumps(snap, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
