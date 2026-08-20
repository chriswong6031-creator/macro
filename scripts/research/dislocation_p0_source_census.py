#!/usr/bin/env python3
"""Price-blind source census for Cross-Issuer Dislocation P0.

This one-time research executable is intentionally unable to read market outcomes.
Its workflow sparse-checks out only official-source / identity artifacts and this
script.  It inventories source depth, clocks, issuer coverage, schema, and candidate
item-code capacity before any event extractor is commissioned.

Authority: research/display only.  It writes no production artifact and performs no
network calls, classification, ranking, gating, sizing, or signal origination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

FORBIDDEN_PATHS = (
    "data/yahoo",
    "data/stocks",
    "data/ohlc",
    "data/stockdata",
    "data/intraday",
    "data/chinaohlc",
    "data/hkohlc",
    "data/canadaohlc",
    "data/intlohlc",
    "data/price_pressure",
    "data/washout_turn",
)

SOURCE_FILES = (
    "data/edgar/material_8k_events.parquet",
    "data/edgar/material_8k_velocity.parquet",
    "data/edgar/earnings_8k_dates.parquet",
    "data/edgar/earnings_8k_dates_coverage.json",
    "data/edgar/earnings_8k_dates_manifest.json",
    "data/edgar/guidance_hits.parquet",
    "data/edgar/bottleneck_hits.parquet",
    "data/edgar/emergence_hits.parquet",
    "data/edgar/dilution_events.parquet",
    "data/edgar/ticker_cik_ledger.json",
    "data/edgar/cik_sic.json",
)

DATE_HINTS = (
    "acceptance",
    "accepted",
    "filing_date",
    "filed",
    "date",
    "timestamp",
    "observed",
    "first_seen",
    "asof",
    "period",
)
IDENTITY_HINTS = ("ticker", "symbol", "cik", "issuer", "company", "accession")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value if not isinstance(value, str) else value[:400]
    return str(value)[:400]


def safe_sample(frame: pd.DataFrame, n: int = 5) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    preferred = [
        col
        for col in frame.columns
        if any(hint in str(col).lower() for hint in IDENTITY_HINTS + DATE_HINTS)
        or str(col).lower() in {
            "form",
            "items",
            "item",
            "event_type",
            "source_url",
            "url",
            "primary_document",
            "exhibit",
            "amount_usd",
            "counterparty",
            "extraction_ok",
        }
    ]
    columns = preferred[:24] or list(frame.columns[:12])
    sample = frame[columns].head(n)
    return [
        {str(col): scalar(value) for col, value in row.items()}
        for row in sample.to_dict(orient="records")
    ]


def date_profile(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for col in frame.columns:
        name = str(col).lower()
        if not any(hint in name for hint in DATE_HINTS):
            continue
        parsed = pd.to_datetime(frame[col], errors="coerce", utc=True)
        non_null = parsed.dropna()
        if non_null.empty:
            continue
        out[str(col)] = {
            "non_null": int(non_null.size),
            "min": non_null.min().isoformat(),
            "max": non_null.max().isoformat(),
            "date_only_share": float(
                sum(
                    isinstance(v, str)
                    and len(v.strip()) == 10
                    and v.strip()[4:5] == "-"
                    and v.strip()[7:8] == "-"
                    for v in frame[col].dropna().head(10000)
                )
                / max(1, min(10000, int(frame[col].notna().sum())))
            ),
        }
    return out


def identity_profile(frame: pd.DataFrame) -> dict[str, int]:
    out: dict[str, int] = {}
    for col in frame.columns:
        name = str(col).lower()
        if any(hint in name for hint in IDENTITY_HINTS):
            out[str(col)] = int(frame[col].dropna().astype(str).nunique())
    return out


def null_profile(frame: pd.DataFrame) -> dict[str, float]:
    return {
        str(col): round(float(frame[col].isna().mean()), 6)
        for col in frame.columns
        if frame[col].isna().any()
    }


def item_counts(frame: pd.DataFrame) -> dict[str, int]:
    if "items" not in frame.columns:
        return {}
    counts: Counter[str] = Counter()
    for raw in frame["items"].dropna().astype(str):
        for item in raw.replace(";", ",").split(","):
            item = item.strip()
            if item:
                counts[item] += 1
    return dict(sorted(counts.items()))


def year_counts(frame: pd.DataFrame) -> dict[str, int]:
    candidates = [
        col
        for col in frame.columns
        if any(hint in str(col).lower() for hint in ("acceptance", "filing_date", "filed", "date"))
    ]
    for col in candidates:
        parsed = pd.to_datetime(frame[col], errors="coerce", utc=True)
        if parsed.notna().sum():
            counts = parsed.dt.year.dropna().astype(int).value_counts().sort_index()
            return {str(year): int(count) for year, count in counts.items()}
    return {}


def summarize_parquet(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    result: dict[str, Any] = {
        "kind": "parquet",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "columns": [str(col) for col in frame.columns],
        "dtypes": {str(col): str(dtype) for col, dtype in frame.dtypes.items()},
        "dates": date_profile(frame),
        "identity_cardinality": identity_profile(frame),
        "null_share": null_profile(frame),
        "year_counts": year_counts(frame),
        "sample": safe_sample(frame),
    }
    if path.name == "material_8k_events.parquet":
        result["item_counts"] = item_counts(frame)
        result["accession_duplicates"] = int(
            frame["accession"].duplicated().sum() if "accession" in frame.columns else 0
        )
        result["extraction_ok_share"] = (
            float(frame["extraction_ok"].fillna(False).astype(bool).mean())
            if "extraction_ok" in frame.columns
            else None
        )
    return result


def json_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": sorted(map(str, value.keys()))[:100],
            "n_keys": len(value),
        }
    if isinstance(value, list):
        keys: set[str] = set()
        for row in value[:1000]:
            if isinstance(row, dict):
                keys.update(map(str, row.keys()))
        return {
            "type": "array",
            "rows": len(value),
            "row_keys": sorted(keys),
            "sample": [
                {str(k): scalar(v) for k, v in row.items()}
                for row in value[:5]
                if isinstance(row, dict)
            ],
        }
    return {"type": type(value).__name__, "value": scalar(value)}


def summarize_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {
        "kind": "json",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "shape": json_shape(payload),
    }
    # Common nested manifests.
    if isinstance(payload, dict):
        for key in ("rows", "events", "filings", "manifest", "items", "data"):
            if key in payload:
                result[f"nested_{key}"] = json_shape(payload[key])
    return result


def source_feasibility(datasets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    material = datasets.get("data/edgar/material_8k_events.parquet", {})
    earnings = datasets.get("data/edgar/earnings_8k_dates.parquet", {})
    item_counts_map = material.get("item_counts") or {}
    return {
        "material_8k_rows": material.get("rows"),
        "material_8k_distinct_tickers": (material.get("identity_cardinality") or {}).get("ticker"),
        "material_8k_years": material.get("year_counts") or {},
        "material_item_counts": item_counts_map,
        "earnings_8k_rows": earnings.get("rows"),
        "earnings_8k_distinct_tickers": (earnings.get("identity_cardinality") or {}).get("ticker"),
        "earnings_8k_years": earnings.get("year_counts") or {},
        "has_acceptance_timestamp_candidate": any(
            "accept" in col.lower()
            for col in earnings.get("columns", [])
        ),
        "candidate_ruling": (
            "LOCAL_CORPUS_CAN_SEED_BUT_CANNOT_BE_ASSUMED_TO_SATISFY_P0; "
            "full source extraction and exact document receipts remain required"
        ),
    }


def run(root: Path) -> dict[str, Any]:
    present_forbidden = [path for path in FORBIDDEN_PATHS if (root / path).exists()]
    if present_forbidden:
        raise RuntimeError(f"price/outcome paths present in blind workspace: {present_forbidden}")

    datasets: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for rel in SOURCE_FILES:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        if path.suffix == ".parquet":
            datasets[rel] = summarize_parquet(path)
        elif path.suffix == ".json":
            datasets[rel] = summarize_json(path)
        else:
            datasets[rel] = {
                "kind": "other",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }

    return {
        "schema": "mastermind.dislocation_p0_source_census.v1",
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
        "blind_boundary": {
            "forbidden_paths": list(FORBIDDEN_PATHS),
            "present_forbidden_paths": present_forbidden,
            "network_used": False,
            "price_or_outcome_read": False,
        },
        "datasets": datasets,
        "missing": missing,
        "feasibility": source_feasibility(datasets),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = run(args.root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.out} ({len(payload['datasets'])} datasets; {len(payload['missing'])} missing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
