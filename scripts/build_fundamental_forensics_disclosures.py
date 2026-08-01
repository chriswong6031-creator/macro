"""Build bounded Filing Forensics disclosure projections from *cached* SEC data.

This is intentionally an explicit off-render command.  It never calls the
network: operators first retain Submissions JSON and primary filing documents in
the immutable SEC caches, then run this command with an acceptance-time cutoff
and a compute clock.  The normal page build only reads the finished private
projection files.

Examples::

    python -m scripts.build_fundamental_forensics_disclosures SMCI MSFT \\
      --as-of 2026-08-01T23:59:59Z --computed-at 2026-08-02T00:10:00Z
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from engine.fundamental_forensics.disclosure_projection import (
    DisclosureProjectionError,
    build_disclosure_projection,
    write_disclosure_projection,
)
from lib import config
from scripts.build_fundamental_forensics import _metadata


log = logging.getLogger("build_fundamental_forensics_disclosures")


def _cik_overrides(values: list[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--cik must use TICKER=CIK")
        ticker, cik = value.split("=", 1)
        ticker = ticker.strip().upper()
        if not ticker or not cik.strip().isdigit():
            raise ValueError("--cik must use TICKER=CIK")
        output[ticker] = int(cik)
    return output


def build_cached_disclosures(
    root: Path,
    tickers: list[str],
    *,
    raw_root: Path,
    archive_root: Path,
    output_root: Path,
    as_of: str,
    computed_at: str,
    cik_overrides: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic private projections without opening any network client."""
    _, _, catalog_ciks = _metadata(root)
    ciks = {**catalog_ciks, **(cik_overrides or {})}
    summaries: list[dict[str, Any]] = []
    for ticker in dict.fromkeys(str(item).strip().upper() for item in tickers if str(item).strip()):
        cik = ciks.get(ticker)
        if cik is None:
            raise DisclosureProjectionError(f"no local CIK mapping for {ticker}; pass --cik {ticker}=CIK")
        projection = build_disclosure_projection(
            raw_root=raw_root,
            archive_root=archive_root,
            ticker=ticker,
            cik=cik,
            as_of=as_of,
            computed_at=computed_at,
        )
        path = write_disclosure_projection(output_root, projection)
        summaries.append(
            {
                "ticker": ticker,
                "cik": projection["issuer"]["cik"],
                "projection_id": projection["projection_id"],
                "tracks_ready": projection["coverage"]["tracks_ready"],
                "tracks_not_evaluable": projection["coverage"]["tracks_not_evaluable"],
                "path": str(path),
            }
        )
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+", help="Ticker symbols with previously retained SEC cache coverage")
    parser.add_argument("--root", type=Path, default=config.ROOT)
    parser.add_argument("--raw-root", type=Path, default=None, help="Immutable submissions cache root")
    parser.add_argument("--archive-root", type=Path, default=None, help="Immutable filing archive cache root")
    parser.add_argument("--output-root", type=Path, default=None, help="Private projection root (defaults to --root)")
    parser.add_argument("--as-of", required=True, help="SEC acceptance-time cutoff with timezone")
    parser.add_argument("--computed-at", required=True, help="Explicit projection compute clock with timezone")
    parser.add_argument("--cik", action="append", default=[], metavar="TICKER=CIK", help="Override local CIK map")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    raw_root = (args.raw_root or root / "data" / "fundamental_forensics" / "raw").resolve()
    archive_root = (args.archive_root or root / "data" / "fundamental_forensics" / "archive").resolve()
    output_root = (args.output_root or root).resolve()
    try:
        summaries = build_cached_disclosures(
            root,
            args.tickers,
            raw_root=raw_root,
            archive_root=archive_root,
            output_root=output_root,
            as_of=args.as_of,
            computed_at=args.computed_at,
            cik_overrides=_cik_overrides(args.cik),
        )
    except (DisclosureProjectionError, ValueError, OSError) as exc:
        log.exception("cached disclosure projection failed: %s", exc)
        print(f"::warning title=fundamental_forensics_disclosures::build skipped ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
