"""Materialize the latest-per-ticker earnings score view from call history.

This is a migration helper, not a new scoring model.  It projects the existing
EquityDesk calibration fields onto the frozen Stage Analysis score contract so
the R2 live view and committed cold-start seed advance together after a delta
import.  The full call history remains the source for season/QoQ surfaces.

Usage::

    python -m scripts.build_earnings_scores_from_history \
      --history data/earnings_calls/history.parquet \
      --scores data/earnings_calls/scores.parquet \
      --manifest data/earnings_calls/manifest.json \
      --seed data/stage_analysis/backfill/earnings_seed.parquet
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from scripts.publish_earnings_r2 import _synth_manifest
from scripts.import_equitydesk_backfill import (
    _derive_tone_word,
    _norm_confidence,
    _norm_performance,
    _norm_sentiment,
    _parse_level_tags,
)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=".tmp.parquet", delete=False
    ) as handle:
        tmp = Path(handle.name)
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp.json", delete=False,
        encoding="utf-8",
    ) as handle:
        tmp = Path(handle.name)
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    try:
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _clean_tag_json(row: pd.Series) -> str:
    tags = _parse_level_tags(row.get("level1_tags"))
    tags.extend(_parse_level_tags(row.get("level2_tags")))
    seen: set[str] = set()
    clean: list[str] = []
    for raw in tags:
        tag = str(raw).strip().lower().replace(" ", "_")
        if tag and tag not in seen:
            seen.add(tag)
            clean.append(tag)
    return json.dumps(clean[:24], ensure_ascii=False, separators=(",", ":"))


def _summary(row: pd.Series) -> str | None:
    for key in ("key_quote", "positive_highlights", "negative_highlights"):
        value = row.get(key)
        if value is not None and not pd.isna(value):
            text = str(value).strip()
            if text:
                return text[:2000]
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _listing_ticker(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"", "NAN", "NONE", "<NA>"}:
        return ""
    parts = text.split()
    return parts[0] if len(parts) == 2 and parts[1] in {"US", "UN", "UW"} else text


def _source_hash(row: pd.Series) -> str:
    material = "|".join(str(row.get(key) or "") for key in (
        "id", "updated_at", "document_ticker", "call_date",
        "earnings_call_sent", "earnings_call_perf", "earnings_call_combined",
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build(history: pd.DataFrame) -> pd.DataFrame:
    """Return one latest score row per normalized document ticker."""
    required = {"document_ticker", "call_date"}
    missing = sorted(required - set(history.columns))
    if missing:
        raise ValueError(f"history contract missing columns: {', '.join(missing)}")
    frame = history.copy()
    frame["ticker"] = frame["document_ticker"].map(_listing_ticker)
    frame["_call_dt"] = pd.to_datetime(frame.get("call_date"), errors="coerce")
    frame = frame[(frame["ticker"] != "") & frame["_call_dt"].notna()]
    frame["_updated_dt"] = pd.to_datetime(
        frame.get("updated_at"), utc=True, errors="coerce",
    )
    frame = frame.sort_values(
        ["_call_dt", "_updated_dt", "fiscal_year", "fiscal_quarter", "ticker"],
        kind="mergesort",
        na_position="first",
    ).drop_duplicates("ticker", keep="last")

    expected = int(history["document_ticker"].map(_listing_ticker).replace("", None).dropna().nunique())
    if len(frame) != expected:
        raise ValueError(
            f"latest-view listing conservation failed: expected={expected} actual={len(frame)}"
        )

    rows: list[dict] = []
    for _, row in frame.iterrows():
        sent = _norm_sentiment(row.get("earnings_call_sent"))
        perf = _norm_performance(row.get("earnings_call_perf"))
        conf = _norm_confidence(row.get("management_confidence_score"))
        quarter_raw = row.get("fiscal_quarter")
        year_raw = row.get("fiscal_year")
        call_year = int(row["_call_dt"].year)
        fiscal_valid = (
            not pd.isna(quarter_raw)
            and not pd.isna(year_raw)
            and 1 <= int(quarter_raw) <= 4
            and call_year - 1 <= int(year_raw) <= call_year + 1
        )
        quarter = f"Q{int(quarter_raw)}" if fiscal_valid else None
        year = int(year_raw) if fiscal_valid else None
        call_date = _optional_text(row.get("call_date")) or ""
        scored_at = (
            _optional_text(row.get("updated_at"))
            or _optional_text(row.get("created_at"))
            or ""
        )
        model = _optional_text(row.get("analysis_model")) or "equitydesk_model_unavailable"
        rows.append({
            "ticker": row["ticker"],
            "quarter": quarter,
            "year": year,
            "call_date": call_date,
            "source": "equitydesk_backfill",
            "model": model,
            "sentiment": sent,
            "performance": perf,
            "confidence": conf,
            "tone_word": _derive_tone_word(sent, conf),
            "tags": _clean_tag_json(row),
            "summary": _summary(row),
            "source_sha256": _source_hash(row),
            "source_record_id": _optional_text(row.get("id")),
            "source_updated_at": _optional_text(row.get("updated_at")),
            "prompt_version": _optional_text(row.get("prompt_version")),
            "analysis_schema_version": _optional_text(
                row.get("analysis_schema_version")
            ),
            "scored_at": scored_at,
        })
    return pd.DataFrame(rows, columns=[
        "ticker", "quarter", "year", "call_date", "source", "model",
        "sentiment", "performance", "confidence", "tone_word", "tags",
        "summary", "source_sha256", "source_record_id", "source_updated_at",
        "prompt_version", "analysis_schema_version", "scored_at",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--seed", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build(pd.read_parquet(args.history))
    if result.empty:
        raise ValueError("refusing to replace earnings stores with an empty latest view")
    _atomic_parquet(result, args.scores)
    if args.seed is not None:
        _atomic_parquet(result, args.seed)
    if args.manifest is not None:
        _atomic_json(_synth_manifest(args.scores, args.history), args.manifest)
    latest = result["call_date"].max() if not result.empty else None
    print(
        f"earnings latest view: {len(result)} tickers, latest={latest}, "
        f"scores={args.scores}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
