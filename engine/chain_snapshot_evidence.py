"""Canonical semantic evidence for private U-CHAIN Parquet snapshots.

The chain-snapshot producer and the Light U-CHAIN projection consumer must hash
the same installed target-bucket rows. Keeping the canonicalizer here avoids a
downstream publisher silently inventing a second digest law.
"""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Sequence

import pandas as pd

CHAIN_SNAPSHOT_DEDUP_KEY = (
    "root", "expiration", "strike", "right", "snapshot_bucket",
)


def canonical_cell(value: object) -> object:
    """Return the strict-JSON scalar used by snapshot semantic receipts."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise RuntimeError("non-finite installed parquet value")
        return value
    if type(value) in {str, int, bool}:
        return value
    raise RuntimeError(
        f"unsupported installed parquet scalar: {type(value).__name__}"
    )


def target_bucket_frame(
    frame: pd.DataFrame,
    root: str,
    bucket: str,
    *,
    dedup_key: Sequence[str],
) -> pd.DataFrame:
    """Select and uniqueness-check one exact producer root/bucket."""
    missing = [column for column in dedup_key if column not in frame.columns]
    if missing:
        raise RuntimeError(f"target-bucket proof is missing columns: {missing}")
    target = frame.loc[
        frame["root"].map(lambda value: type(value) is str and value == root)
        & frame["snapshot_bucket"].astype(str).eq(bucket)
    ].copy()
    if target.empty:
        raise RuntimeError(f"installed parquet has no {root}/{bucket} target rows")
    if target.duplicated(subset=list(dedup_key)).any():
        raise RuntimeError(
            f"installed parquet has duplicate {root}/{bucket} target rows"
        )
    return target


def frame_content_sha256(
    frame: pd.DataFrame,
    *,
    dedup_key: Sequence[str],
) -> str:
    """Hash one frame with the producer's deterministic semantic law."""
    columns = sorted(str(column) for column in frame.columns)
    ordered = frame.sort_values(
        [column for column in dedup_key if column in frame.columns],
        kind="stable",
    ).reset_index(drop=True)
    payload = {
        "columns": columns,
        "rows": [
            [canonical_cell(value) for value in row]
            for row in ordered.loc[:, columns].itertuples(index=False, name=None)
        ],
    }
    return sha256(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    """Hash exact file bytes without assigning them publication authority."""
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
