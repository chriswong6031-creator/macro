"""Publish or restore the Filing Forensics disclosure-projection bundle.

Explicit operator/lane command only: it has no scheduler hook of its own, never
renders the public shell, and never publishes private browser state.  Two
directions, one target list:

* ``--publish`` reads every target's canonical private projection from
  ``<root>/data/fundamental_forensics/private/disclosures/`` and publishes them
  as ONE immutable bundle plus a compare-and-swap ``latest`` pointer.  A single
  missing or invalid projection refuses the whole publication — a partial
  bundle would silently shrink the entitled coverage the workbench attaches.
* ``--restore`` reads the published bundle and writes those same twelve files
  back.  This is what the nightly engine job runs as its hard gate: one bounded
  pointer GET plus one bounded bundle GET, constant in the size of the SEC
  source store the projections were built from.

The producing lane is ``.github/workflows/filing-forensics-sec.yml`` (02:30
UTC); the engine job consumes what that lane published.  A red producer leaves
the pointer at the last COMPLETE bundle, so the engine renders stale-but-complete
(warn beyond ``--warn-age-days``, refuse beyond ``--fail-age-days``) instead of
losing the whole nightly render to one SEC outage.

Every clock is explicit — there is no ``now()`` fallback::

    python -m scripts.fundamental_forensics_disclosure_bundle --publish \\
      --targets-file config/fundamental_forensics/wave2_targets.v1.json \\
      --published-at 2026-08-08T02:40:00Z

    python -m scripts.fundamental_forensics_disclosure_bundle --restore \\
      --targets-file config/fundamental_forensics/wave2_targets.v1.json \\
      --now 2026-08-08T06:00:00Z

``--local-store /path`` selects the repository's LocalStore adapter for a
dry-run or test; otherwise the private Research R2 configuration
(``R2_RESEARCH_BUCKET`` plus private credentials) is required.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.fundamental_forensics_acquisition import (
    AcquisitionError,
    DEFAULT_MAX_TICKERS,
    normalize_targets,
)  # noqa: E402
from engine.fundamental_forensics.disclosure_bundle import (
    DisclosureBundleError,
    build_disclosure_bundle,
    publish_disclosure_bundle,
    restore_disclosure_bundle,
)  # noqa: E402
from engine.fundamental_forensics.disclosure_projection import (
    DisclosureProjectionError,
    disclosure_projection_path,
    read_disclosure_projection,
)  # noqa: E402
from engine.fundamental_forensics.models import parse_utc  # noqa: E402
from engine.fundamental_forensics.source_sync import (
    SourceSyncError,
    build_private_source_store,
)  # noqa: E402
from lib import config  # noqa: E402
from scripts.run_fundamental_forensics_wave2 import OperatorFlowError, load_targets_file  # noqa: E402


log = logging.getLogger("fundamental_forensics_disclosure_bundle")


def _targets(args: argparse.Namespace) -> tuple[str, ...]:
    """Resolve the explicit target list: pinned file first, then CLI extras."""
    merged = list(load_targets_file(args.targets_file))
    merged.extend(args.target or [])
    # The cap is the acquisition lane's own default so one file cannot mean two
    # different universes in the producer and the consumer.
    return tuple(item.ticker for item in normalize_targets(merged, max_tickers=DEFAULT_MAX_TICKERS))


def _publish(args: argparse.Namespace, tickers: tuple[str, ...]) -> dict:
    if not args.published_at:
        raise DisclosureBundleError("--published-at is required with --publish")
    root = Path(args.root)
    projections = {
        ticker: read_disclosure_projection(disclosure_projection_path(root, ticker))
        for ticker in tickers
    }
    bundle = build_disclosure_bundle(projections, published_at=args.published_at)
    store = build_private_source_store(local_dir=args.local_store)
    return publish_disclosure_bundle(store, bundle)


def _restore(args: argparse.Namespace, tickers: tuple[str, ...]) -> dict:
    if not args.now:
        raise DisclosureBundleError("--now is required with --restore")
    store = build_private_source_store(local_dir=args.local_store)
    return restore_disclosure_bundle(
        store,
        output_root=Path(args.root),
        expected_tickers=tickers,
        now=args.now,
        warn_age_days=args.warn_age_days,
        fail_age_days=args.fail_age_days,
    )


def _age_days(result: dict, now: str) -> float:
    published = parse_utc(str(result.get("published_at") or ""), field="published_at")
    current = parse_utc(now, field="now")
    if published is None or current is None:  # pragma: no cover - both are validated first
        return 0.0
    return (current - published).total_seconds() / 86400.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    direction = parser.add_mutually_exclusive_group(required=True)
    direction.add_argument("--publish", action="store_true", help="Publish the bundle from local private projections")
    direction.add_argument("--restore", action="store_true", help="Restore the published bundle into local private projections")
    parser.add_argument("--targets-file", type=Path, required=True, help="Pinned explicit target list (single source of truth)")
    parser.add_argument("--target", action="append", metavar="TICKER=CIK", help="Extra explicit issuer target merged after the file")
    parser.add_argument("--root", type=Path, default=config.ROOT, help="Repository root holding data/fundamental_forensics/private/disclosures")
    parser.add_argument("--published-at", default=None, help="Explicit UTC publication clock (required with --publish)")
    parser.add_argument("--now", default=None, help="Explicit UTC read clock for the age gate (required with --restore)")
    parser.add_argument("--warn-age-days", type=float, default=3.0, help="Annotate a stale bundle beyond this age")
    parser.add_argument("--fail-age-days", type=float, default=21.0, help="Refuse a bundle beyond this age")
    parser.add_argument("--local-store", type=Path, default=None, help="Use LocalStore instead of private Research R2 (dry-run/test)")
    args = parser.parse_args(argv)
    try:
        tickers = _targets(args)
        if args.publish:
            outcome = _publish(args, tickers)
        else:
            outcome = _restore(args, tickers)
            if outcome.get("stale_warning"):
                print(
                    "::warning title=fundamental_forensics_disclosure_bundle::"
                    f"published disclosure bundle is {_age_days(outcome, args.now):.1f} days old "
                    f"(warn beyond {args.warn_age_days}d, refuse beyond {args.fail_age_days}d) — "
                    "the filing-forensics-sec lane has not published since "
                    f"{outcome.get('published_at')}",
                    flush=True,
                )
    except (
        AcquisitionError,
        DisclosureBundleError,
        DisclosureProjectionError,
        OperatorFlowError,
        SourceSyncError,
        ValueError,
        OSError,
    ) as exc:
        log.exception("disclosure bundle command failed: %s", exc)
        print(
            f"::warning title=fundamental_forensics_disclosure_bundle::command stopped ({type(exc).__name__}: {exc})",
            flush=True,
        )
        return 1
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
