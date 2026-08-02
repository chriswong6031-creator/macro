"""Build Company Theme Exposure from a verified Company Intelligence generation.

This CLI is intentionally parquet- and network-free.  It consumes the exact
marker plus immutable tree already published by Company Intelligence, then
joins only current curated basket membership through the canonical crosswalk.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.company_intelligence.contracts import ContractError
from engine.company_theme_exposure.views import (
    build_bundle,
    load_company_generation,
    load_crosswalk,
    load_json,
    write_generation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-intelligence-dir", type=Path, required=True)
    parser.add_argument("--membership", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--theme-state", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--as-of", default=None, help="ISO freshness reference (defaults to pinned CI generated_at)")
    args = parser.parse_args(argv)
    try:
        contexts, ci_manifest = load_company_generation(args.company_intelligence_dir)
        membership = load_json(args.membership)
        crosswalk = load_crosswalk(args.crosswalk)
        # Missing state is a valid partial projection.  A malformed state is
        # represented by an empty mapping so the closed view contract emits an
        # explicit ``theme_state_invalid`` receipt instead of quietly calling
        # corrupt data "missing".
        theme_state = None
        if args.theme_state and args.theme_state.exists():
            try:
                theme_state = load_json(args.theme_state)
            except ContractError:
                theme_state = {}
        exposures, manifest = build_bundle(
            contexts,
            company_manifest=ci_manifest,
            membership=membership or {},
            crosswalk=crosswalk,
            theme_state=theme_state,
            as_of=args.as_of,
        )
        generation = write_generation(args.out_dir, exposures, manifest)
    except ContractError as exc:
        print(f"company theme exposure: build refused: {exc}", file=sys.stderr)
        return 1
    print(
        "company theme exposure: "
        f"generation={manifest['generation_id']} companies={manifest['company_count']} "
        f"exposures={manifest['exposure_count']} path={generation}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
