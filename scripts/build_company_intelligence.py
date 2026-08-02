"""Build deterministic, context-only Company Intelligence generation objects.

Parquet handling is deliberately isolated to this CLI.  The projection itself
accepts list[dict] values, so contract tests and consumers do not need pandas.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.company_intelligence.contracts import ContractError, normalize_quarter, normalize_year, parse_date, safe_ticker
from engine.company_intelligence.views import build_bundle, write_generation


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_parquet_rows(path: Path) -> list[dict]:
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("pandas with a parquet engine is required only for this CLI") from exc
    return pd.read_parquet(path).to_dict(orient="records")


def _history_identity(row: dict) -> None:
    """Validate only the immutable join identity before a batch projection.

    The pure projection remains fail-closed for callers. The operational CLI,
    however, quarantines an isolated corrupt upstream row so one typo cannot
    prevent thousands of healthy company views from advancing.
    """
    safe_ticker(row.get("document_ticker") or row.get("ticker") or row.get("symbol"))
    normalize_year(row.get("fiscal_year") if row.get("fiscal_year") is not None else row.get("year"))
    normalize_quarter(row.get("fiscal_quarter") if row.get("fiscal_quarter") is not None else row.get("quarter"))
    parse_date(row.get("call_date") if row.get("call_date") is not None else row.get("date"), field="call_date")


def _quarantine_invalid_history(rows: list[dict]) -> tuple[list[dict], int]:
    valid: list[dict] = []
    rejected = 0
    for row in rows:
        try:
            _history_identity(row)
        except ContractError:
            rejected += 1
            continue
        valid.append(row)
    return valid, rejected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--earnings-manifest", type=Path, required=True)
    parser.add_argument("--tx-index", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--as-of", default=None, help="Optional ISO date freshness reference")
    args = parser.parse_args(argv)
    history_rows, rejected_history = _quarantine_invalid_history(_read_parquet_rows(args.history))
    contexts, manifest = build_bundle(
        history_rows,
        _read_parquet_rows(args.scores),
        earnings_manifest=_read_json(args.earnings_manifest),
        tx_index=_read_json(args.tx_index),
        as_of=args.as_of,
        history_rows_rejected=rejected_history,
    )
    if rejected_history:
        print(f"company intelligence: quarantined invalid history rows={rejected_history}", file=sys.stderr)
    generation_dir = write_generation(args.out_dir, contexts, manifest)
    print(
        f"company intelligence: generation={manifest['generation_id']} "
        f"companies={manifest['company_count']} events={manifest['event_count']} "
        f"path={generation_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
