"""Build coverage-aligned, context-only per-company institutional 13F sidecars."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.company_intelligence.contracts import ContractError
from engine.company_institutional_context.views import build_bundle, load_company_intelligence, load_config, write_generation
from engine.company_institutional_context.contracts import bytes_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-intelligence-dir", type=Path, required=True)
    parser.add_argument("--smart-money-config", type=Path, default=Path("config.yml"))
    parser.add_argument("--share-class-equivalence", type=Path, default=Path("config/share_class_equiv.yml"))
    parser.add_argument("--snapshot-root", type=Path, default=Path("data/smart_money"))
    parser.add_argument("--universe-membership", type=Path, default=Path("data/universe/membership.parquet"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--as-of", default=None, help="ISO build date; defaults to pinned CI generated_at")
    args = parser.parse_args(argv)
    try:
        contexts, ci_manifest = load_company_intelligence(args.company_intelligence_dir)
        managers, config_sha = load_config(args.smart_money_config)
        generated, manifest = build_bundle(
            contexts,
            company_manifest=ci_manifest,
            smart_money_config=managers,
            smart_money_config_sha256=config_sha,
            share_class_equivalence_sha256=bytes_sha256(args.share_class_equivalence),
            universe_membership_sha256=bytes_sha256(args.universe_membership),
            snapshot_root=args.snapshot_root,
            universe_membership=args.universe_membership,
            as_of=args.as_of,
        )
        generation = write_generation(args.out_dir, generated, manifest)
    except ContractError as exc:
        print(f"company institutional context: build refused: {exc}", file=sys.stderr)
        return 1
    print(
        "company institutional context: "
        f"generation={manifest['generation_id']} companies={manifest['company_count']} "
        f"covered={manifest['covered_company_count']} period={manifest['consensus_period']} path={generation}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
