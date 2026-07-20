"""scripts/import_equitydesk_backfill.py — SGA W5 competitor-backfill importer.

Reads the two EquityDesk snapshot files and produces:

  1. data/stage_analysis/backfill/equitydesk_overview.parquet  (COMMITTED yardstick)
     All 6 536 rows, all regions, exact EquityDesk fields preserved.

  2. data/earnings_calls/backfill_analysis.parquet  (gitignored — large)
     Full per-call unified_analysis flattened: our_ticker, region, call_date,
     fiscal_qtr, model_used, prompt_version, call_summary, positive_factors(json),
     negative_factors(json), guidance(json), hot_topics(json), their sub-scores.

  3. Seed data/earnings_calls/scores.parquet  (gitignored — R2-transported lane)
     Rows in our canonical schema; mapped from EquityDesk earnings via the join
     described in the W5 mapping below.  Idempotent upsert keyed
     (ticker, quarter, year, source='equitydesk_backfill').

── W5 MAPPING (pinned; amend only with a SGA ruling) ──────────────────────────

Join strategy
  US names: overview.ticker is our clean ticker.
  overview rows are indexed by ticker.  earnings.document_ticker OR
  earnings.ticker_tradingview matched against overview.ticker gives us the
  clean OUR ticker.  Fallback: strip exchange suffix from document_ticker
  (VIMIAN.ST → VIMIAN; strip any ' XX' exchange codes too).

Sentiment normalisation
  sentiment(−1..1) = clip((their_sent − 12) / 18, −1, 1)
  [sent 30→+1, 12→0, −6→−1]  — their range ~-10..30, 12 is the neutral midpoint
  (their ≥24 gate corresponds to our ≥0.67 = "upbeat/confident" range).

Performance normalisation
  performance(0..10) = clip((their_perf + 12) / 2.4, 0, 10)
  [perf +12→10, 0→5, −12→0]  — their perf range ~-12..+12.

confidence  = management_confidence_score / 10   (0..1)

tone_word   derived by feeding `sentiment` through the SAME thresholds used in
            engine.stage_analysis._tone_word (≥0.3→upbeat, ≤-0.3→downbeat,
            else steady).  A fuller word comes from the confidence level:
            high confidence (≥0.7) → "confident" / "defensive";
            low confidence (≤0.3)  → "uncertain" / "guarded".

positive_highlights / negative_highlights
  from unified_analysis.positive_factors / negative_factors (list, cap 3,
  strip to short phrases, run through engine.earnings_qual._scrub_trading_verbs).

tags        mapped through engine.earnings_qual._clean_tags (keeps only the
            14-item pinned taxonomy; most sector tags will drop — correct).

source_sha256  engine.earnings_qual.source_sha256(call_summary or '')

summary     unified_analysis.call_summary  (new column added in W5)

source      'equitydesk_backfill'
────────────────────────────────────────────────────────────────────────────────

Usage
  python -m scripts.import_equitydesk_backfill [--src DIR] [--root DIR] [--dry-run]

  --src  directory containing overview.json and earnings.json
         (default ~/Documents/Cluade/equitydesk_backfill)
  --root repo root  (default: auto-detected from __file__)
  --dry-run  parse + report stats but write NO files
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo-root bootstrap
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPT_DIR.parent
if str(_REPO_ROOT_DEFAULT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_DEFAULT))


# ---------------------------------------------------------------------------
# Tone-word derivation (mirrors engine.stage_analysis._tone_word thresholds,
# with richer bucketing using confidence).
# ---------------------------------------------------------------------------
def _derive_tone_word(sentiment: float | None, confidence: float | None) -> str | None:
    """Map (sentiment, confidence) -> tone word.

    Uses the same TONE_UP/TONE_DOWN thresholds as engine.stage_analysis._tone_word
    (0.3 / -0.3), then refines with confidence:
      high conf (≥0.7) + positive  → 'confident'
      high conf (≥0.7) + negative  → 'defensive'
      low conf (≤0.3)  + positive  → 'uncertain'
      low conf (≤0.3)  + negative  → 'guarded'
      middle range (positive)      → 'upbeat' / 'steady'
      middle range (negative)      → 'downbeat'
    """
    if sentiment is None:
        return None
    try:
        s = float(sentiment)
    except (TypeError, ValueError):
        return None
    conf = None
    if confidence is not None:
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            pass

    if s >= 0.3:
        if conf is not None and conf >= 0.7:
            return "confident"
        if conf is not None and conf <= 0.3:
            return "uncertain"
        return "upbeat"
    if s <= -0.3:
        if conf is not None and conf >= 0.7:
            return "defensive"
        if conf is not None and conf <= 0.3:
            return "guarded"
        return "downbeat"
    # neutral band
    return "steady"


# ---------------------------------------------------------------------------
# Exchange-suffix stripping for fallback ticker cleaning
# ---------------------------------------------------------------------------
_EXCHANGE_SUFFIX_RE = re.compile(
    r"[.\s]("
    r"SS|SZ|HK|L|PA|AS|DE|F|SW|IM|ST|OL|HE|CO|MC|AX|"
    r"NS|BO|KS|KQ|TW|SI|BK|JK|MX|BR|SA|"
    r"US|NY|NQ|O|V|T"
    r")$",
    re.IGNORECASE,
)


def _clean_ticker(raw: str) -> str:
    """Strip exchange suffix and normalize to uppercase."""
    t = raw.strip()
    m = _EXCHANGE_SUFFIX_RE.search(t)
    if m:
        t = t[: m.start()].strip()
    return t.upper()


# ---------------------------------------------------------------------------
# Join map: build {our_ticker → list[earnings_row_idx]}
# ---------------------------------------------------------------------------
def _build_join_map(overview: list[dict], earnings: list[dict]) -> dict[str, int]:
    """Returns {earnings_row_index → our_ticker (str)}.

    Tries:
      1. earnings.document_ticker matches overview.ticker (exact, uppercase)
      2. earnings.ticker_tradingview matches overview.ticker
      3. cleaned document_ticker as fallback (US names only)
    """
    # Index overview by ticker (uppercase).
    ov_tickers: set[str] = {str(r["ticker"]).upper() for r in overview if r.get("ticker")}

    idx_to_our: dict[int, str] = {}
    for idx, er in enumerate(earnings):
        # Strategy 1: document_ticker vs overview.ticker
        dt = str(er.get("document_ticker") or "").strip().upper()
        if dt and dt in ov_tickers:
            idx_to_our[idx] = dt
            continue
        # Strategy 2: ticker_tradingview vs overview.ticker
        tv = str(er.get("ticker_tradingview") or "").strip().upper()
        # ticker_tradingview may contain "NASDAQ:AAPL" prefix
        if ":" in tv:
            tv = tv.split(":", 1)[1].strip().upper()
        if tv and tv in ov_tickers:
            idx_to_our[idx] = tv
            continue
        # Strategy 3: clean document_ticker (strip exchange suffix)
        if dt:
            cleaned = _clean_ticker(dt)
            if cleaned and cleaned in ov_tickers:
                idx_to_our[idx] = cleaned
                continue
        # No match — use cleaned document_ticker as-is (non-US names)
        if dt:
            idx_to_our[idx] = _clean_ticker(dt) or dt
    return idx_to_our


# ---------------------------------------------------------------------------
# Normalisation helpers (W5 mapping formulas, pinned)
# ---------------------------------------------------------------------------
def _norm_sentiment(their_sent: Any) -> float | None:
    """sentiment(−1..1) = clip((their_sent − 12) / 18, −1, 1)."""
    try:
        v = float(their_sent)
    except (TypeError, ValueError):
        return None
    r = (v - 12.0) / 18.0
    return max(-1.0, min(1.0, r))


def _norm_performance(their_perf: Any) -> float | None:
    """performance(0..10) = clip((their_perf + 12) / 2.4, 0, 10)."""
    try:
        v = float(their_perf)
    except (TypeError, ValueError):
        return None
    r = (v + 12.0) / 2.4
    return max(0.0, min(10.0, r))


def _norm_confidence(mgmt_conf: Any) -> float | None:
    """confidence(0..1) = management_confidence_score / 10."""
    try:
        v = float(mgmt_conf)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, v / 10.0))


# ---------------------------------------------------------------------------
# Tag / highlight coercion (reuse engine.earnings_qual functions)
# ---------------------------------------------------------------------------
def _parse_level_tags(raw: Any) -> list[str]:
    """Coerce level1_tags / level2_tags (stored as JSON string or list)."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(t) for t in v]
        except Exception:  # noqa: BLE001
            return [s] if s else []
    return []


def _parse_json_field(raw: Any) -> Any:
    """Parse a field that might be a JSON string, dict, list, or scalar."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:  # noqa: BLE001
            return s
    return raw


def _to_json_str(obj: Any) -> str:
    """Serialize to compact JSON string for parquet storage."""
    if obj is None:
        return "[]"
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return "[]"


# ---------------------------------------------------------------------------
# Fiscal quarter parser from unified_analysis.meta.fiscal_qtr ("2026-Q2")
# ---------------------------------------------------------------------------
def _parse_fiscal_qtr(fiscal_qtr_str: Any) -> tuple[str | None, int | None]:
    """Parse "2026-Q2" → (quarter='Q2', year=2026)."""
    if not fiscal_qtr_str or not isinstance(fiscal_qtr_str, str):
        return None, None
    s = fiscal_qtr_str.strip()
    # Expect "YYYY-QN" or "QN-YYYY" or "QN YYYY"
    m = re.match(r"(\d{4})[- ]Q(\d)", s, re.IGNORECASE)
    if m:
        return f"Q{m.group(2)}", int(m.group(1))
    m = re.match(r"Q(\d)[- ](\d{4})", s, re.IGNORECASE)
    if m:
        return f"Q{m.group(1)}", int(m.group(2))
    return None, None


# ---------------------------------------------------------------------------
# Highlight cleaning (reuse scrub from earnings_qual, fail-open)
# ---------------------------------------------------------------------------
def _scrub_highlights(raw_list: Any, *, cap: int = 3) -> list[str]:
    """Scrub trading verbs from a list of highlight strings; cap at 3."""
    try:
        from engine.earnings_qual import _clean_highlights  # noqa: PLC0415
        # _clean_highlights expects a list
        lst = raw_list if isinstance(raw_list, list) else []
        return _clean_highlights(lst)[:cap]
    except Exception:  # noqa: BLE001
        # Fallback: basic truncation
        if not isinstance(raw_list, list):
            return []
        out = []
        for item in raw_list:
            if isinstance(item, str) and item.strip():
                out.append(item.strip()[:200])
                if len(out) >= cap:
                    break
        return out


def _clean_tags_eq(raw: Any) -> list[str]:
    """Run through earnings_qual._clean_tags (taxonomy filter)."""
    parsed = _parse_level_tags(raw)
    try:
        from engine.earnings_qual import _clean_tags  # noqa: PLC0415
        return _clean_tags(parsed)
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Main importer
# ---------------------------------------------------------------------------
def run(
    src: Path,
    root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Load both source files, build all three outputs, print stats.

    Returns a stats dict for tests to inspect.
    """
    import pandas as pd  # noqa: PLC0415

    # ── Load source files ────────────────────────────────────────────────────
    overview_path = src / "overview.json"
    earnings_path = src / "earnings.json"

    if not overview_path.exists():
        raise FileNotFoundError(f"overview.json not found in {src}")
    if not earnings_path.exists():
        raise FileNotFoundError(f"earnings.json not found in {src}")

    log.info("Loading overview.json …")
    with overview_path.open(encoding="utf-8") as fh:
        overview: list[dict] = json.load(fh)
    log.info("Loaded %d overview rows", len(overview))

    log.info("Loading earnings.json …")
    with earnings_path.open(encoding="utf-8") as fh:
        earnings: list[dict] = json.load(fh)
    log.info("Loaded %d earnings rows", len(earnings))

    # ── 1. equitydesk_overview.parquet ───────────────────────────────────────
    log.info("Building equitydesk_overview.parquet …")
    ov_rows: list[dict] = []
    for r in overview:
        row = {k: v for k, v in r.items()}
        # Parse JSON-string tag fields into Python lists, re-serialise as JSON str
        row["level1_tags"] = _to_json_str(_parse_level_tags(r.get("level1_tags")))
        row["level2_tags"] = _to_json_str(_parse_level_tags(r.get("level2_tags")))
        ov_rows.append(row)
    ov_df = pd.DataFrame(ov_rows)
    # Region counts
    region_counts: dict[str, int] = {}
    for r in overview:
        reg = str(r.get("region") or "UNKNOWN").upper()
        region_counts[reg] = region_counts.get(reg, 0) + 1

    # ── 2 & 3. Build join map then iterate earnings rows ─────────────────────
    log.info("Building join map (earnings → overview ticker) …")
    idx_to_our = _build_join_map(overview, earnings)

    # Load our taxonomy-filter function
    try:
        from engine.earnings_qual import source_sha256 as _sha256  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        import hashlib

        def _sha256(text: str) -> str:  # type: ignore[misc]
            return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    # Count US name join quality
    us_total = sum(1 for r in earnings if (r.get("gics_sector") or r.get("document_ticker", "").endswith("") or True))
    # Better: count earnings rows for US overview entries
    us_ov_tickers: set[str] = {
        str(r["ticker"]).upper() for r in overview
        if str(r.get("region") or "").upper() == "USA" and r.get("ticker")
    }
    us_earnings_matched = 0
    us_earnings_total = 0

    ba_rows: list[dict] = []   # backfill_analysis.parquet rows
    score_rows: list[dict] = []  # scores.parquet seed rows

    for idx, er in enumerate(earnings):
        our_ticker = idx_to_our.get(idx, "")
        region = "USA" if our_ticker in us_ov_tickers else "INTL"

        if our_ticker in us_ov_tickers:
            us_earnings_total += 1

        ua = er.get("unified_analysis") or {}
        meta = ua.get("meta") or {}
        _cs_raw = ua.get("call_summary")
        call_summary = str(_cs_raw or "").strip()  # raw form — kept only for a stable sha
        # EquityDesk's call_summary is a STRUCTURED object, not prose; its readable
        # narrative is .outlook_summary. Never surface the raw dict on the page.
        if isinstance(_cs_raw, dict):
            summary_prose = str(_cs_raw.get("outlook_summary") or "").strip() or None
        elif isinstance(_cs_raw, str):
            summary_prose = _cs_raw.strip() or None
        else:
            summary_prose = None
        fiscal_qtr_str = meta.get("fiscal_qtr") or ""
        quarter, year = _parse_fiscal_qtr(fiscal_qtr_str)
        call_date = str(er.get("call_date") or "").strip()
        model_used = str(ua.get("model_used") or "").strip()
        prompt_version = str(ua.get("prompt_version") or "").strip()

        # ── backfill_analysis row ────────────────────────────────────────────
        ba_row = {
            "our_ticker": our_ticker,
            "region": region,
            "call_date": call_date,
            "fiscal_qtr": fiscal_qtr_str,
            "model_used": model_used,
            "prompt_version": prompt_version,
            "call_summary": summary_prose or call_summary,
            "positive_factors": _to_json_str(ua.get("positive_factors")),
            "negative_factors": _to_json_str(ua.get("negative_factors")),
            "guidance": _to_json_str(ua.get("guidance")),
            "hot_topics": _to_json_str(ua.get("hot_topics")),
            # Their sub-scores
            "call_positivity_score": er.get("call_positivity_score"),
            "management_confidence_score": er.get("management_confidence_score"),
            "analyst_criticism_score": er.get("analyst_criticism_score"),
            "future_outlook_score": er.get("future_outlook_score"),
            "earnings_call_sent": er.get("earnings_call_sent"),
            "earnings_call_perf": er.get("earnings_call_perf"),
            "earnings_call_combined": er.get("earnings_call_combined"),
        }
        ba_rows.append(ba_row)

        # ── scores.parquet seed row ──────────────────────────────────────────
        if not our_ticker:
            continue
        their_sent = er.get("earnings_call_sent")
        their_perf = er.get("earnings_call_perf")
        mgmt_conf = er.get("management_confidence_score")

        sentiment = _norm_sentiment(their_sent)
        performance = _norm_performance(their_perf)
        confidence = _norm_confidence(mgmt_conf)
        tone_word = _derive_tone_word(sentiment, confidence)

        # highlights from unified_analysis factors (list of dicts or strings)
        pos_factors = ua.get("positive_factors") or []
        neg_factors = ua.get("negative_factors") or []
        # Factors may be dicts with a "factor" key or plain strings
        def _factors_to_strs(lst: Any) -> list[str]:
            if not isinstance(lst, list):
                return []
            out = []
            for item in lst:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    s = (item.get("factor") or item.get("title") or
                         item.get("description") or item.get("text") or "")
                    if s:
                        out.append(str(s))
            return out

        pos_strs = _factors_to_strs(pos_factors)
        neg_strs = _factors_to_strs(neg_factors)
        pos_highlights = _scrub_highlights(pos_strs)
        neg_highlights = _scrub_highlights(neg_strs)

        # Tags: combine level1 + level2 tags through taxonomy filter
        l1 = _parse_level_tags(er.get("level1_tags"))
        l2 = _parse_level_tags(er.get("level2_tags"))
        tags = _clean_tags_eq(l1 + l2)

        sha = _sha256(call_summary or "")

        score_row: dict[str, Any] = {
            "ticker": our_ticker,
            "quarter": quarter,
            "year": year,
            "call_date": call_date,
            "source": "equitydesk_backfill",
            "model": model_used or "equitydesk",
            "sentiment": sentiment,
            "performance": performance,
            "confidence": confidence,
            "tone_word": tone_word,
            "positive_highlights": json.dumps(pos_highlights, ensure_ascii=False),
            "negative_highlights": json.dumps(neg_highlights, ensure_ascii=False),
            "tags": json.dumps(tags, ensure_ascii=False),
            "source_sha256": sha,
            "scored_at": call_date + "T00:00:00+00:00" if call_date else "",
            "summary": (summary_prose or (pos_strs[0] if pos_strs else None) or None),
        }
        if score_row["summary"]:
            score_row["summary"] = str(score_row["summary"])[:2000]
        score_rows.append(score_row)

        if our_ticker in us_ov_tickers:
            us_earnings_matched += 1

    # ── Stats ────────────────────────────────────────────────────────────────
    tag_hits = sum(1 for r in score_rows if json.loads(r["tags"]) != [])
    tag_match_rate = tag_hits / len(score_rows) if score_rows else 0.0
    us_join_rate = us_earnings_matched / us_earnings_total if us_earnings_total else 0.0

    stats: dict[str, Any] = {
        "overview_rows": len(overview),
        "earnings_rows": len(earnings),
        "region_counts": region_counts,
        "us_earnings_total": us_earnings_total,
        "us_earnings_matched": us_earnings_matched,
        "us_join_rate": us_join_rate,
        "scores_seeded": len(score_rows),
        "tag_match_rate": tag_match_rate,
    }

    # ── Print summary ────────────────────────────────────────────────────────
    print("\n═══ EquityDesk backfill import ═══")
    print(f"  overview rows: {len(overview):,}")
    for reg, n in sorted(region_counts.items()):
        print(f"    {reg}: {n:,}")
    print(f"  earnings rows: {len(earnings):,}")
    print(f"  US earnings rows: {us_earnings_total:,}")
    print(f"  US join rate: {us_join_rate:.1%}  ({us_earnings_matched:,}/{us_earnings_total:,})")
    print(f"  Scores seeded: {len(score_rows):,}")
    print(f"  Tag match rate: {tag_match_rate:.1%}  ({tag_hits:,} rows with ≥1 taxonomy tag)")

    if dry_run:
        print("  [dry-run] No files written.")
        return stats

    # ── Write 1: equitydesk_overview.parquet (COMMITTED yardstick) ───────────
    ov_out = root / "data" / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    ov_out.parent.mkdir(parents=True, exist_ok=True)
    ov_df.to_parquet(ov_out, index=False)
    log.info("Wrote %s  (%d rows)", ov_out, len(ov_df))
    print(f"  [1] {ov_out}  ({len(ov_df):,} rows)")

    # ── Write 2: backfill_analysis.parquet (gitignored — large) ──────────────
    ba_df = pd.DataFrame(ba_rows)
    ba_out = root / "data" / "earnings_calls" / "backfill_analysis.parquet"
    ba_out.parent.mkdir(parents=True, exist_ok=True)
    ba_df.to_parquet(ba_out, index=False)
    log.info("Wrote %s  (%d rows)", ba_out, len(ba_df))
    print(f"  [2] {ba_out}  ({len(ba_df):,} rows)  [gitignored]")

    # ── Write 3: COMMITTED earnings seed ──────────────────────────────────────
    # The backfill is a cold-start SEED, not fresh worker output — it belongs on a
    # committed path so every render/nightly has earnings context before the Qwen
    # worker produces anything. engine.stage_analysis._load_earnings_scores reads
    # this seed UNDER the live (gitignored, R2-transported) scores.parquet, which
    # the worker overlays per ticker. Curated to exactly the columns the engine reads.
    seed_out = root / "data" / "stage_analysis" / "backfill" / "earnings_seed.parquet"
    seed_cols = [
        "ticker", "quarter", "year", "call_date", "source", "model",
        "sentiment", "performance", "confidence", "tone_word", "tags",
        "summary", "scored_at",
    ]
    sc_df = pd.DataFrame(score_rows)
    sc_df = sc_df.reindex(columns=seed_cols)
    # Dedup on (ticker, quarter, year, source), keep last
    sc_df = sc_df.drop_duplicates(
        subset=["ticker", "quarter", "year", "source"], keep="last"
    ).reset_index(drop=True)
    seed_out.parent.mkdir(parents=True, exist_ok=True)
    sc_df.to_parquet(seed_out, index=False)
    log.info("Wrote %s (%d rows)", seed_out, len(sc_df))
    print(f"  [3] {seed_out}  ({len(sc_df):,} rows)  [committed cold-start seed]")

    print("═══════════════════════════════════\n")
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import EquityDesk backfill data (SGA W5)."
    )
    p.add_argument(
        "--src",
        default="~/Documents/Cluade/equitydesk_backfill",
        help="Directory containing overview.json and earnings.json",
    )
    p.add_argument(
        "--root",
        default=None,
        help="Repo root (default: auto-detected from script location)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report stats but write no files",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    src = Path(args.src).expanduser().resolve()
    root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else _REPO_ROOT_DEFAULT
    )
    run(src, root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
