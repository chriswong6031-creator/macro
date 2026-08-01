"""Run the explicit, no-render Filing Forensics Wave-2 operator flow.

The command intentionally has no scheduler hook and never calls the public
page/state render.  It is for a collect lane or an operator who wants one
bounded sequence in this fixed order: restore -> acquire -> build projections
-> sync immutable SEC sources.

First bootstrap (no remote source snapshot exists yet)::

    python -m scripts.run_fundamental_forensics_wave2 \\
      --target SMCI=0001375365 --target MSFT=0000789019 \\
      --as-of 2026-08-01T23:59:59Z --recorded-at 2026-08-02T00:05:00Z \\
      --computed-at 2026-08-02T00:10:00Z \\
      --acquire --build-projections --sync

Warm recovery/update from the private Research R2 snapshot::

    python -m scripts.run_fundamental_forensics_wave2 \\
      --target SMCI=0001375365 --target MSFT=0000789019 \\
      --as-of 2026-08-01T23:59:59Z --recorded-at 2026-08-02T00:05:00Z \\
      --computed-at 2026-08-02T00:10:00Z \\
      --restore --acquire --build-projections --sync

``--local-store /path`` selects the existing LocalStore adapter for a dry-run
or test.  Otherwise restore/sync require the existing private Research R2
configuration (``R2_RESEARCH_BUCKET`` and private credentials).  This command
does not print credentials and is never called by render.

By default, an SEC outage for one explicit target is represented as
``status=partial`` plus a durable per-ticker receipt and the command exits zero
so healthy names can accrue.  A scheduled lane that must not publish a broad
state with partial disclosure coverage should add ``--require-complete-acquisition``;
that option stops before projection or source sync when any target is partial.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from collectors.edgar_forensics import _user_agent
from collectors.fundamental_forensics_acquisition import (
    AcquisitionError,
    AcquisitionTarget,
    acquire_bounded_filings,
    normalize_targets,
)
from engine.fundamental_forensics.source_sync import (
    SourceSyncError,
    build_private_source_store,
    restore_source_roots,
    sync_source_roots,
)
from engine.research_vault.r2_store import Store
from engine.fundamental_forensics.models import parse_utc, utc_text
from lib import config
from scripts.build_fundamental_forensics_disclosures import build_cached_disclosures


log = logging.getLogger("run_fundamental_forensics_wave2")


class OperatorFlowError(RuntimeError):
    """The explicit collect-lane operation cannot safely continue."""


def _normalized_clock(value: str, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise OperatorFlowError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - CLI requires every clock
        raise OperatorFlowError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def run_operator_flow(
    *,
    root: Path,
    targets: Iterable[str | AcquisitionTarget | tuple[str, int | str]],
    as_of: str,
    recorded_at: str,
    computed_at: str,
    restore: bool = False,
    acquire: bool = False,
    build_projections: bool = False,
    sync: bool = False,
    require_complete_acquisition: bool = False,
    raw_root: Path | None = None,
    archive_root: Path | None = None,
    projection_root: Path | None = None,
    local_store: str | Path | None = None,
    snapshot_id: str | None = None,
    max_tickers: int = 12,
    max_submissions_bytes: int = 16 * 1024 * 1024,
    max_document_bytes: int = 16 * 1024 * 1024,
    max_ticker_bytes: int = 80 * 1024 * 1024,
    max_total_bytes: int = 256 * 1024 * 1024,
    min_interval_seconds: float = 0.12,
    store: Store | None = None,
) -> dict[str, Any]:
    """Execute selected Wave-2 actions in safe fixed order, never rendering UI/state."""
    if not any((restore, acquire, build_projections, sync)):
        raise OperatorFlowError("select at least one action: --restore, --acquire, --build-projections, or --sync")
    resolved_root = Path(root).resolve()
    normalized = normalize_targets(targets, max_tickers=max_tickers)
    normalized_as_of = _normalized_clock(as_of, field="as_of")
    normalized_recorded_at = _normalized_clock(recorded_at, field="recorded_at")
    normalized_computed_at = _normalized_clock(computed_at, field="computed_at")
    resolved_raw = (raw_root or resolved_root / "data" / "fundamental_forensics" / "raw").resolve()
    resolved_archive = (archive_root or resolved_root / "data" / "fundamental_forensics" / "archive").resolve()
    resolved_projection = (projection_root or resolved_root).resolve()
    active_store = store
    if restore or sync:
        active_store = active_store or build_private_source_store(local_dir=local_store)
    result: dict[str, Any] = {
        "schema": "fundamental_forensics.wave2_operator_flow/v1",
        "targets": [item.to_dict() for item in normalized],
        "actions": {
            "restore": bool(restore),
            "acquire": bool(acquire),
            "build_projections": bool(build_projections),
            "sync": bool(sync),
            "require_complete_acquisition": bool(require_complete_acquisition),
        },
        "clocks": {
            "as_of": normalized_as_of,
            "recorded_at": normalized_recorded_at,
            "computed_at": normalized_computed_at,
        },
        "results": {},
    }
    # This sequence is intentionally fixed even if a caller lists CLI flags in
    # another order: restore a durable cache before acquiring, then project
    # only verified cache bytes, and commit the next immutable remote snapshot last.
    if restore:
        if active_store is None:  # defensive; build_private_source_store raises first
            raise OperatorFlowError("restore requires a private source store")
        restored = restore_source_roots(
            raw_root=resolved_raw,
            archive_root=resolved_archive,
            store=active_store,
            snapshot_id=snapshot_id,
        )
        result["results"]["restore"] = restored.to_dict()
    if acquire:
        acquired = acquire_bounded_filings(
            targets=normalized,
            raw_root=resolved_raw,
            archive_root=resolved_archive,
            user_agent=_user_agent(resolved_root),
            as_of=normalized_as_of,
            recorded_at=normalized_recorded_at,
            max_tickers=max_tickers,
            max_submissions_bytes=max_submissions_bytes,
            max_document_bytes=max_document_bytes,
            max_ticker_bytes=max_ticker_bytes,
            max_total_bytes=max_total_bytes,
            min_interval_seconds=min_interval_seconds,
        )
        result["results"]["acquire"] = acquired
        if require_complete_acquisition and acquired.get("status") != "complete":
            raise OperatorFlowError(
                "bounded acquisition returned partial coverage; refusing projection/sync because complete coverage was required"
            )
    if build_projections:
        projections = build_cached_disclosures(
            resolved_root,
            [item.ticker for item in normalized],
            raw_root=resolved_raw,
            archive_root=resolved_archive,
            output_root=resolved_projection,
            as_of=normalized_as_of,
            computed_at=normalized_computed_at,
            cik_overrides={item.ticker: int(item.cik) for item in normalized},
        )
        result["results"]["build_projections"] = projections
    if sync:
        if active_store is None:  # defensive; build_private_source_store raises first
            raise OperatorFlowError("sync requires a private source store")
        snapshot = sync_source_roots(
            raw_root=resolved_raw,
            archive_root=resolved_archive,
            store=active_store,
            snapshot_at=normalized_recorded_at,
        )
        result["results"]["sync"] = snapshot.to_dict()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", required=True, metavar="TICKER=CIK", help="Explicit issuer target; repeat for each ticker")
    parser.add_argument("--as-of", required=True, help="SEC acceptance-time cutoff with timezone")
    parser.add_argument("--recorded-at", required=True, help="Explicit UTC recording clock with timezone")
    parser.add_argument("--computed-at", required=True, help="Explicit projection compute clock with timezone")
    parser.add_argument("--restore", action="store_true", help="Restore the private immutable source snapshot first")
    parser.add_argument("--acquire", action="store_true", help="Fetch only SEC Submissions plus up to two 10-K/two 10-Q primary filings")
    parser.add_argument("--build-projections", action="store_true", help="Build cached disclosure projections; never renders the workbench")
    parser.add_argument("--sync", action="store_true", help="Read-back-verify raw/archive into the private immutable source store last")
    parser.add_argument(
        "--require-complete-acquisition",
        action="store_true",
        help="Fail before projection/sync when any explicit target has partial SEC acquisition coverage",
    )
    parser.add_argument("--raw-root", type=Path, default=None, help="Local immutable Submissions cache root")
    parser.add_argument("--archive-root", type=Path, default=None, help="Local immutable filing archive root")
    parser.add_argument("--projection-root", type=Path, default=None, help="Private disclosure projection output root")
    parser.add_argument("--local-store", type=Path, default=None, help="Use LocalStore instead of private Research R2 (dry-run/test)")
    parser.add_argument("--snapshot-id", default=None, help="Restore a specific immutable source snapshot instead of latest")
    parser.add_argument("--max-tickers", type=int, default=12, help="Lower-only bounded target cap (hard ceiling 32)")
    parser.add_argument("--max-submissions-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--max-document-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--max-ticker-bytes", type=int, default=80 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--min-interval-seconds", type=float, default=0.12, help="SEC pacing interval; collector never goes below 0.1s")
    parser.add_argument("--root", type=Path, default=config.ROOT)
    args = parser.parse_args(argv)
    try:
        outcome = run_operator_flow(
            root=args.root,
            targets=args.target,
            as_of=args.as_of,
            recorded_at=args.recorded_at,
            computed_at=args.computed_at,
            restore=args.restore,
            acquire=args.acquire,
            build_projections=args.build_projections,
            sync=args.sync,
            require_complete_acquisition=args.require_complete_acquisition,
            raw_root=args.raw_root,
            archive_root=args.archive_root,
            projection_root=args.projection_root,
            local_store=args.local_store,
            snapshot_id=args.snapshot_id,
            max_tickers=args.max_tickers,
            max_submissions_bytes=args.max_submissions_bytes,
            max_document_bytes=args.max_document_bytes,
            max_ticker_bytes=args.max_ticker_bytes,
            max_total_bytes=args.max_total_bytes,
            min_interval_seconds=args.min_interval_seconds,
        )
    except (AcquisitionError, OperatorFlowError, SourceSyncError, ValueError, OSError) as exc:
        log.exception("Wave-2 operator flow failed: %s", exc)
        print(f"::warning title=fundamental_forensics_wave2::operator flow stopped ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
