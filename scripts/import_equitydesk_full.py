"""EquityDesk full backfill importer.

Reads every /Users/chriswong/Documents/Cluade/equitydesk_backfill/full/*.json
and writes committed parquet seeds under data/stage_analysis/backfill/.

Design rules:
- Fail-open: missing / malformed files are skipped with a log line (never crash).
- Atomic writes: write to a temp file then os.replace().
- No new heavy deps beyond pandas/pyarrow (already available).
- Earnings is ~595MB; parsed with json.load (no ijson) but kept memory-safe by
  selecting only the required columns immediately and not holding the full dict.
- Total committed footprint: earnings_calls_text.parquet (summary + unified_analysis)
  is written but listed in .gitignore; the numeric/tag seed stays committed.
- Display-tier epistemics: is_context_only flag on manifest (never gates/sizing).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
BACKFILL_SRC = Path(os.environ.get(
    "EQUITYDESK_BACKFILL",
    "/Users/chriswong/Documents/Cluade/equitydesk_backfill/full",
))
SEED_DIR = _REPO_ROOT / "data" / "stage_analysis" / "backfill"
MANIFEST_PATH = SEED_DIR / "_manifest.json"

# Size threshold (bytes) above which we split text cols into a separate file
_TEXT_SPLIT_THRESHOLD_BYTES = 40 * 1024 * 1024  # 40 MB

# ---------------------------------------------------------------------------
# Earnings columns
# ---------------------------------------------------------------------------
_EC_NUMERIC_COLS = [
    "document_ticker",
    "company_ticker",
    "company_name",
    "fiscal_quarter",
    "fiscal_year",
    "call_date",
    "gics_sector",
    "gics_industry_group",
    "gics_industry",
    "gics_subindustry",        # note: source uses gics_subindustry (no _)
    "earnings_call_sent",
    "earnings_call_perf",
    "earnings_call_combined",
    "earnings_call_pop",
    "analysts_count",           # Earnings surface needs these (item 11)
    "questions_count",
    "call_positivity_score",
    "management_confidence_score",
    "analyst_criticism_score",
    "future_outlook_score",
    "revenue_growth",
    "eps_growth",
    "gross_margin",
    "positive_highlights",
    "negative_highlights",
    "key_quote",
    "level1_tags",
    "level2_tags",
    "file_path",
]
_EC_TEXT_COLS = [
    "summary",
    "unified_analysis",
]
# The full committed set (numeric seed) is numeric + highlights/tags/key_quote/file_path.
# Text-only cols land in earnings_calls_text.parquet (gitignored).

# Stage table columns to keep
_STAGE_COLS = [
    "ticker", "region", "name_ui", "sata_score", "sata_change_1w",
    "stage_flag", "stage_detailed", "weeks_in_stage", "is_stage2_start",
    "breakout_confirmed", "rs_ratio", "rs_trend_52w", "mansfield_rs",
    "mansfield_rs_change", "atr_14w", "atr_ext", "close", "sma_30w",
    "industry_id", "industry_name", "industry_percentile", "industry_label",
    "industry_bucket",
    "sub_industry_id", "sub_industry_name", "sub_industry_percentile",
    "sub_industry_label", "sub_industry_bucket",
    "gics_industry", "gics_sub_industry",
    "data_as_of_date",
    # extra cols that may be present in the file (kept if present)
    "tickerb", "ticker_tradingview", "week_end", "date",
]

# Research columns
_RESEARCH_COLS = [
    "tickerb", "summary_thesis_answer", "claude_reasoning_analysis",
    "openai_reasoning_analysis", "gemini_reasoning_research_url",
    "model_used", "tier", "response_type", "ticker_ui",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _src(name: str) -> Path | None:
    """Return source JSON path or None if missing."""
    p = BACKFILL_SRC / f"{name}.json"
    if not p.exists():
        log.warning("SKIP  %s not found", p)
        return None
    return p


def _load_json(path: Path) -> list[dict]:
    """Load a JSON file (expected: list of dicts).  Returns [] on error."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            log.warning("SKIP  %s — top-level not a list (got %s)", path.name, type(data).__name__)
            return []
        return data
    except Exception as exc:
        log.warning("SKIP  %s — parse error: %s", path.name, exc)
        return []


def _select_cols(df: pd.DataFrame, want: list[str]) -> pd.DataFrame:
    """Return df with only the subset of wanted columns that actually exist."""
    present = [c for c in want if c in df.columns]
    return df[present].copy()


def _atomic_write(df: pd.DataFrame, dest: Path) -> None:
    """Write parquet atomically via a temp file in the same directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=dest.parent, suffix=".tmp.parquet", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        df.to_parquet(tmp_path, index=False, engine="pyarrow")
        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _record(manifest: dict, name: str, df: pd.DataFrame, source_file: str) -> None:
    manifest[name] = {
        "rows": len(df),
        "cols": list(df.columns),
        "source_file": source_file,
        "imported_utc": None,
        "is_context_only": True,
        "display_only": True,
    }
    log.info("WRITE %-45s rows=%-6d cols=%d", name + ".parquet", len(df), len(df.columns))


# ---------------------------------------------------------------------------
# Individual seed writers
# ---------------------------------------------------------------------------

# NOTE: the "overview" seed is NOT written here. The engines read the W5
# yardstick `equitydesk_overview.parquet` (produced by import_equitydesk_backfill.py
# with the richer schema — analysts_count/questions_count/earnings/combined_rating).
# Writing a second `overview.parquet` from overview_combined_table shipped an
# orphan seed nothing reads — dropped so there is ONE overview seed (item 11).


def write_stage_daily(manifest: dict) -> None:
    src = _src("stageanalysis_stock_sata_stage_rs_ui_all_data")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    df = _select_cols(df, _STAGE_COLS)
    _atomic_write(df, SEED_DIR / "stage_daily.parquet")
    _record(manifest, "stage_daily", df, src.name)


def write_stage_weekly(manifest: dict) -> None:
    src = _src("stageanalysis_stock_sata_stage_rs_ui_all_data_weekly_view")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    df = _select_cols(df, _STAGE_COLS)
    _atomic_write(df, SEED_DIR / "stage_weekly.parquet")
    _record(manifest, "stage_weekly", df, src.name)


def write_price_ma_weekly(manifest: dict) -> None:
    src = _src("stageanalysis_stock_price_ma_weekly_3y")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "price_ma_weekly.parquet")
    _record(manifest, "price_ma_weekly", df, src.name)


def write_industry_flows(manifest: dict) -> None:
    src = _src("industry_flows")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "industry_flows.parquet")
    _record(manifest, "industry_flows", df, src.name)


def write_subindustry_flows(manifest: dict) -> None:
    src = _src("subindustry_flows")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "subindustry_flows.parquet")
    _record(manifest, "subindustry_flows", df, src.name)


def write_industry_ranks(manifest: dict) -> None:
    src = _src("stageanalysis_industry_ranks_weekly")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "industry_ranks.parquet")
    _record(manifest, "industry_ranks", df, src.name)


def write_ec_industry(manifest: dict) -> None:
    src = _src("earnings_call_gics_industry_weekly")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "ec_industry.parquet")
    _record(manifest, "ec_industry", df, src.name)


def write_top_performers(manifest: dict) -> None:
    src = _src("top_performers_by_industries")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "top_performers.parquet")
    _record(manifest, "top_performers", df, src.name)


def write_top_performers_horizontal(manifest: dict) -> None:
    src = _src("top_performers_by_industries_leaders_laggards_horizontal_view")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "top_performers_horizontal.parquet")
    _record(manifest, "top_performers_horizontal", df, src.name)


def write_altdata_gt(manifest: dict) -> None:
    src = _src("alt_data_gt_companies_matched")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "altdata_gt.parquet")
    _record(manifest, "altdata_gt", df, src.name)


def write_altdata_reddit(manifest: dict) -> None:
    src = _src("alt_data_reddit_companies_matched")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "altdata_reddit.parquet")
    _record(manifest, "altdata_reddit", df, src.name)


def write_altdata_tiktok(manifest: dict) -> None:
    src = _src("alt_data_tiktok_companies_matched")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "altdata_tiktok.parquet")
    _record(manifest, "altdata_tiktok", df, src.name)


def write_altdata_wiki(manifest: dict) -> None:
    src = _src("alt_data_wiki_companies_matched")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "altdata_wiki.parquet")
    _record(manifest, "altdata_wiki", df, src.name)


def write_trending_gt(manifest: dict) -> None:
    src = _src("google_trends_trending_topics")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "trending_gt.parquet")
    _record(manifest, "trending_gt", df, src.name)


def write_trending_subreddits(manifest: dict) -> None:
    src = _src("trending_subreddits")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "trending_subreddits.parquet")
    _record(manifest, "trending_subreddits", df, src.name)


def write_top_growing_subreddits(manifest: dict) -> None:
    src = _src("top_growing_subreddits")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "top_growing_subreddits.parquet")
    _record(manifest, "top_growing_subreddits", df, src.name)


def write_top_growing_tiktok(manifest: dict) -> None:
    src = _src("top_growing_tiktok_pages")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "top_growing_tiktok.parquet")
    _record(manifest, "top_growing_tiktok", df, src.name)


def write_wiki_top_pages(manifest: dict) -> None:
    src = _src("wiki_top_pages")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "wiki_top_pages.parquet")
    _record(manifest, "wiki_top_pages", df, src.name)


def write_research(manifest: dict) -> None:
    src = _src("company_generated_info")
    if src is None:
        return
    log.info("LOAD  company_generated_info.json (~119MB) ...")
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    df = _select_cols(df, _RESEARCH_COLS)
    # dedupe on tickerb keeping last (most recent)
    if "tickerb" in df.columns:
        df = df.drop_duplicates(subset=["tickerb"], keep="last")
    _atomic_write(df, SEED_DIR / "research.parquet")
    _record(manifest, "research", df, src.name)


def write_ticker_map(manifest: dict) -> None:
    src = _src("ticker_mappings")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    # dedupe on tickerb
    if "tickerb" in df.columns:
        df = df.drop_duplicates(subset=["tickerb"], keep="last")
    _atomic_write(df, SEED_DIR / "ticker_map.parquet")
    _record(manifest, "ticker_map", df, src.name)


def write_companies(manifest: dict) -> None:
    src = _src("companies")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    if "tickerb" in df.columns:
        df = df.drop_duplicates(subset=["tickerb"], keep="last")
    _atomic_write(df, SEED_DIR / "companies.parquet")
    _record(manifest, "companies", df, src.name)


def write_volume(manifest: dict) -> None:
    src = _src("volume_analytics")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "volume.parquet")
    _record(manifest, "volume", df, src.name)


def write_news(manifest: dict) -> None:
    src = _src("news_history")
    if src is None:
        return
    data = _load_json(src)
    if not data:
        return
    df = pd.DataFrame(data)
    _atomic_write(df, SEED_DIR / "news.parquet")
    _record(manifest, "news", df, src.name)


def write_earnings_calls(manifest: dict) -> None:
    """Parse earnings_call_data.json memory-safely.

    The file is ~595 MB with 50,053 rows.  We use json.load (no ijson
    available) but immediately project only the columns we need.  Dict
    references for unused columns are dropped right away, so peak memory is
    roughly: 595 MB (raw JSON string) + ~200 MB (selected columns as Python
    objects) + parquet output.  On a modern machine with 16 GB+ this is fine;
    on tighter boxes the large-file path issues a warning.

    Column split:
    - earnings_calls.parquet  — numeric + tags + highlights (COMMITTED)
    - earnings_calls_text.parquet — summary + unified_analysis (GITIGNORED)
    """
    src = _src("earnings_call_data")
    if src is None:
        return

    file_size = src.stat().st_size
    log.info(
        "LOAD  earnings_call_data.json (%.0fMB) — large file, may take ~30s …",
        file_size / 1024 / 1024,
    )
    data = _load_json(src)
    if not data:
        return

    log.info("PARSE %d earnings call rows", len(data))

    # Project only needed columns immediately to free the rest.
    # Union keys across a SAMPLE of rows (not row-0 only): source rows are not
    # guaranteed to carry every key (a sparse first row would silently drop a
    # column present later, e.g. analysts_count/questions_count) — item 11.
    available: set[str] = set()
    for row in data[:2000]:
        if isinstance(row, dict):
            available |= row.keys()

    # Build rows for numeric seed
    num_want = [c for c in _EC_NUMERIC_COLS if c in available]
    txt_want = [c for c in _EC_TEXT_COLS if c in available]

    # Dedupe on (document_ticker, fiscal_quarter, fiscal_year, call_date)
    # keeping last (most recently updated)
    df_num = pd.DataFrame(
        [{k: row.get(k) for k in num_want} for row in data]
    )

    dedup_keys = [c for c in ["document_ticker", "fiscal_quarter", "fiscal_year", "call_date"]
                  if c in df_num.columns]
    if dedup_keys:
        df_num = df_num.drop_duplicates(subset=dedup_keys, keep="last")

    # Type coercions for numeric columns
    for col in ["fiscal_quarter", "fiscal_year", "analysts_count", "questions_count",
                "call_positivity_score", "management_confidence_score",
                "analyst_criticism_score", "future_outlook_score"]:
        if col in df_num.columns:
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce").astype("Int64")
    for col in ["earnings_call_sent", "earnings_call_perf", "earnings_call_combined"]:
        if col in df_num.columns:
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce").astype("Int64")
    for col in ["revenue_growth", "eps_growth", "gross_margin", "earnings_call_pop"]:
        if col in df_num.columns:
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce")

    # Estimate committed size; split text if total would exceed threshold
    # Always split text cols into a separate file regardless of size,
    # because unified_analysis (nested dicts) is very heavy.
    dest_num = SEED_DIR / "earnings_calls.parquet"
    dest_txt = SEED_DIR / "earnings_calls_text.parquet"

    _atomic_write(df_num, dest_num)
    _record(manifest, "earnings_calls", df_num, src.name)

    # Check committed size
    committed_size = dest_num.stat().st_size
    if committed_size > _TEXT_SPLIT_THRESHOLD_BYTES:
        log.warning(
            "earnings_calls.parquet is %.1f MB > 40 MB threshold — "
            "consider dropping more text cols",
            committed_size / 1024 / 1024,
        )

    # Write text parquet (gitignored)
    if txt_want:
        # Include the dedupe keys in text file too for joins
        txt_with_keys = [c for c in dedup_keys if c not in txt_want] + txt_want
        txt_available = [c for c in txt_with_keys if c in available]
        df_txt_rows = [{k: row.get(k) for k in txt_available} for row in data]
        df_txt = pd.DataFrame(df_txt_rows)
        if dedup_keys:
            df_txt = df_txt.drop_duplicates(
                subset=[c for c in dedup_keys if c in df_txt.columns], keep="last"
            )
        # unified_analysis is a mixed-type column (some rows are dicts, some
        # are strings or None).  pyarrow cannot serialise mixed struct/non-struct
        # in a single array, so we coerce to a JSON string for storage.
        if "unified_analysis" in df_txt.columns:
            def _to_json_str(v: Any) -> str | None:
                if v is None:
                    return None
                if isinstance(v, str):
                    return v
                try:
                    return json.dumps(v, ensure_ascii=False)
                except Exception:
                    return str(v)
            df_txt["unified_analysis"] = df_txt["unified_analysis"].map(_to_json_str)
        _atomic_write(df_txt, dest_txt)
        txt_size = dest_txt.stat().st_size / 1024 / 1024
        log.info(
            "WRITE earnings_calls_text.parquet (GITIGNORED) rows=%d cols=%d size=%.1fMB",
            len(df_txt), len(df_txt.columns), txt_size,
        )
        manifest["earnings_calls_text"] = {
            "rows": len(df_txt),
            "cols": list(df_txt.columns),
            "source_file": src.name,
            "imported_utc": None,
            "is_context_only": True,
            "display_only": True,
            "gitignored": True,
            "note": "text-only cols (summary, unified_analysis); not committed",
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}

    # Stage tables (no overview seed here — see note above write_stage_daily)
    write_stage_daily(manifest)
    write_stage_weekly(manifest)
    write_price_ma_weekly(manifest)

    # Industry / flows
    write_industry_flows(manifest)
    write_subindustry_flows(manifest)
    write_industry_ranks(manifest)
    write_ec_industry(manifest)

    # Top performers
    write_top_performers(manifest)
    write_top_performers_horizontal(manifest)

    # Alt-data: matched
    write_altdata_gt(manifest)
    write_altdata_reddit(manifest)
    write_altdata_tiktok(manifest)
    write_altdata_wiki(manifest)

    # Alt-data: raw trending topics
    write_trending_gt(manifest)
    write_trending_subreddits(manifest)
    write_top_growing_subreddits(manifest)
    write_top_growing_tiktok(manifest)
    write_wiki_top_pages(manifest)

    # Research + identity
    write_research(manifest)
    write_ticker_map(manifest)
    write_companies(manifest)

    # Volume + news
    write_volume(manifest)
    write_news(manifest)

    # Earnings (large — do last)
    write_earnings_calls(manifest)

    # Write manifest
    with tempfile.NamedTemporaryFile(
        dir=SEED_DIR, suffix=".tmp.json", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(manifest, tmp, indent=2)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, MANIFEST_PATH)
    log.info("WROTE _manifest.json (%d tables)", len(manifest))

    # Summary
    total_rows = sum(v["rows"] for v in manifest.values() if "rows" in v)
    log.info("DONE  %d tables, %d total rows", len(manifest), total_rows)

    # Report committed file sizes
    committed_bytes = 0
    for p in SEED_DIR.glob("*.parquet"):
        if p.name != "earnings_calls_text.parquet":
            committed_bytes += p.stat().st_size
    log.info("COMMITTED parquet total: %.1f MB", committed_bytes / 1024 / 1024)

    # Report sizes of all seeds
    log.info("--- Seed sizes ---")
    for p in sorted(SEED_DIR.glob("*.parquet")):
        gitignored = p.name in ("earnings_calls_text.parquet",)
        label = " [GITIGNORED]" if gitignored else ""
        log.info("  %-55s %.2f MB%s", p.name, p.stat().st_size / 1024 / 1024, label)


if __name__ == "__main__":
    main()
