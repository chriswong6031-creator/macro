"""Case-exact Massive/Polygon ticker identity and artifact paths.

Massive's vendor ticker space is case-sensitive. In particular, ``TPC`` and
``TpC`` (and ``BCPC`` and ``BCpC``) are different securities. The ordinary
per-ticker store layout remains unchanged for all-uppercase symbols, while a
mixed-case symbol is placed below a hex-keyed directory so the full path is
distinct even on a case-insensitive filesystem such as default macOS APFS.

This module deliberately has no pandas/config imports. Lightweight consumers
such as the Hot Tape pack can decode store paths without importing a collector.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


CASE_ARTIFACT_DIR = "__case_v1"


def vendor_join_key(value: object) -> str:
    """Return the case-exact vendor identity used at Massive join boundaries.

    Dot-to-dash is the repository's established universe spelling conversion;
    case is never folded because it is part of the vendor identity.
    """
    return str(value or "").strip().replace(".", "-")


def artifact_relative_path(ticker: object) -> Path:
    """Return a backward-compatible, case-insensitive-safe parquet path.

    Existing all-uppercase artifacts keep their historical ``TICKER.parquet``
    names. Mixed-case identities use ``__case_v1/<UTF-8 hex>.parquet``; ASCII
    case changes alter hex digits, so APFS cannot fold two identities together.
    """
    raw = str(ticker or "").strip()
    if not raw:
        raise ValueError("Massive ticker must be non-empty")
    if raw == raw.upper():
        return Path(f"{raw}.parquet")
    return Path(CASE_ARTIFACT_DIR) / f"{raw.encode('utf-8').hex()}.parquet"


def ticker_from_artifact_path(path: Path | str, store_dir: Path | str) -> str:
    """Decode a ticker from an artifact path produced by this module."""
    p = Path(path)
    root = Path(store_dir)
    try:
        rel = p.relative_to(root)
    except ValueError:
        rel = p
    if len(rel.parts) == 2 and rel.parts[0] == CASE_ARTIFACT_DIR:
        try:
            return bytes.fromhex(Path(rel.parts[1]).stem).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""
    return rel.stem


def is_canonical_artifact_posix(value: object) -> bool:
    """Return True iff *value* is exactly ``artifact_relative_path`` output.

    The public R2 listing must name either a legacy all-uppercase
    ``TICKER.parquet`` object or ``__case_v1/<UTF-8 hex>.parquet``. Mixed-case
    names at the store root, traversal, extra slashes, and hex that does not
    round-trip the producer are not canonical.
    """
    if type(value) is not str or not value or "\\" in value:
        return False
    if value != Path(value).as_posix() or value in {".", ".."}:
        return False
    decoded = ticker_from_artifact_path(value, ".")
    if not decoded:
        return False
    try:
        return artifact_relative_path(decoded).as_posix() == value
    except ValueError:
        return False


def iter_artifact_paths(store_dir: Path | str) -> Iterator[Path]:
    """Yield legacy uppercase and v1 mixed-case parquet artifacts."""
    root = Path(store_dir)
    yield from root.glob("*.parquet")
    case_dir = root / CASE_ARTIFACT_DIR
    if case_dir.is_dir():
        yield from case_dir.glob("*.parquet")
