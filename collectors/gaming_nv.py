"""Nevada Gaming Control Board (NV GCB) + LVCVA monthly — stub collector.

BACKFILL PATH (documented, not auto-executed):
  NV GCB: https://gaming.nv.gov/index.aspx?page=149
    → Monthly Gaming Revenue Reports (PDF) and Excel since ~2001.
    → Recent 24 months (2024-06 onward) are parseable if time allows.
  LVCVA: https://www.lvcva.com/research/visitor-statistics/
    → Monthly visitor statistics (Las Vegas arrivals, hotel occupancy).
    → PDF / Excel, 2019+; correlates with gaming volumes.

WHY STUBS NOW:
  NV GCB publishes PDFs with complex multi-column layouts; pdfminer can
  extract text but the table geometry requires a bespoke parser for each
  vintage of the form.  A FULL backfill is a multi-day engineering task and
  would exceed the W4 Phase-0 time budget.  The stub:
    (1) Documents the exact download URLs and parse strategy.
    (2) Provides parse_nv_pdf() for manual invocation on recent files.
    (3) Wires the adapter to the nightly collector registry so a future agent
        can drop in a complete parser without changing the call site.

The W4 Phase-0 study uses NY + NJ + PGCB data (machine-readable Excel), which
provides adequate multi-state coverage for the consolidated nowcast and
event-study hypotheses.  NV GCB adds Nevada-specific land-based revenue that
is not currently needed for the operator list (WYNN, LVS, MGM, CZR have direct
NV exposure but they are large enough that state-level disclosure is not
a primary nowcast input).

PIT contract: NV GCB releases data 30-45 days after month-end.
  release_date = fetch date; period_end = last calendar day of the month.

Nightly wiring (for consolidation):
  from collectors.gaming_nv import NVGamingAdapter
  # Add NVGamingAdapter() to the nightly registry.
  # Until the full parser lands, the adapter returns an empty dict and logs
  # a BLOCKED notice.  The run_status.json circuit breaker will NOT trip
  # because expected_failure is set.
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Generator

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "gaming_tape"
OUT_DIR_NAME = "nv_monthly"

NV_GCB_INDEX = "https://gaming.nv.gov/index.aspx?page=149"
LVCVA_STATS = "https://www.lvcva.com/research/visitor-statistics/"

# -----------------------------------------------------------------------
# BACKFILL STRATEGY (documented for the follow-up build agent)
# -----------------------------------------------------------------------
# NV GCB monthly PDFs have three sections: (A) Area summary, (B) Operator
# detail, (C) Game-type breakdown.  We want section B.
# Parse approach:
#   1. Download PDF from the link matching "Gaming Revenue Report <month> <year>"
#   2. Use pdfminer.high_level.extract_text() to get raw text.
#   3. Split on the section B marker (e.g., "UNRESTRICTED LICENSE HOLDERS").
#   4. Use regex to extract rows: each licensee occupies 1-3 lines with the
#      format:  <name>  <num_locations>  <revenue_$>  <pct_change>
#   5. Aggregate to operator level using OPERATOR_ALIASES.
#   6. Store as period_end / operator / gross_revenue_usd / n_locations.
#
# NV GCB also publishes an Excel summary (recent months only) at:
#   https://gaming.nv.gov/modules/showdocument.aspx?documentid=<id>
# where documentid increments roughly monthly.  The most recent id as of
# 2026-07-06 is ~22500.  A range scan of ~50 ids finds recent months:
#   for i in range(22400, 22600): try GET, check Content-Type
# This is the recommended first approach for the recent-24-month partial build.


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _iter_recent_excel_ids(start: int = 22400, end: int = 22600) -> Generator[tuple[int, str], None, None]:
    """Yield (document_id, url) for likely recent NV GCB Excel files.
    Uses HEAD requests to avoid downloading non-Excel payloads.
    Call this when implementing the full NV parser.
    """
    base = "https://gaming.nv.gov/modules/showdocument.aspx?documentid={}"
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; MacroDashboard/1.0)"
    for doc_id in range(start, end):
        url = base.format(doc_id)
        try:
            r = session.head(url, timeout=10, allow_redirects=True)
            ct = r.headers.get("Content-Type", "")
            if "excel" in ct or "spreadsheet" in ct or "openxml" in ct:
                yield (doc_id, url)
                time.sleep(0.3)
        except Exception:
            pass


def parse_nv_pdf_stub(raw: bytes, period_end: date, release_date: date) -> pd.DataFrame:
    """
    STUB — PDF parser for NV GCB monthly reports.

    This is a placeholder that extracts whatever pdfminer can easily grab.
    It will NOT parse the full operator table correctly in most vintages.
    Replace the body of this function with a production parser when the
    full NV backfill is scheduled.

    Returns an empty DataFrame (honoring the partial-data contract).
    """
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        text = extract_text(io.BytesIO(raw))
        log.debug("NV PDF extracted %d chars (stub — not fully parsed)", len(text))
    except Exception as exc:
        log.warning("NV PDF pdfminer failed: %s", exc)
    # Return empty — stub does not attempt structural parse
    return pd.DataFrame(columns=[
        "period_end", "release_date", "state", "operator", "gross_revenue_usd"
    ])


class NVGamingAdapter:
    """Stub adapter for NV GCB + LVCVA.

    Returns empty dict and logs BLOCKED until a full PDF/Excel parser is built.
    expected_failure prevents the circuit breaker from tripping.
    """

    name = "gaming_nv"
    group = GROUP
    stale_after_days = 35
    expected_failure = (
        "NV GCB parser not yet implemented; PDF layout requires bespoke parser. "
        "See collectors/gaming_nv.py BACKFILL STRATEGY for the build path."
    )

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out_dir = config.data_dir() / GROUP / OUT_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        log.warning(
            "gaming_nv: BLOCKED — %s", self.expected_failure
        )
        return {}

    def stored_series(self) -> list[str]:
        return ["nv_monthly"]

    def last_good_date(self) -> date | None:
        p = config.data_dir() / GROUP / OUT_DIR_NAME / "panel.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df.empty:
            return None
        return pd.to_datetime(df["period_end"]).max().date()


def _cli():
    parser = argparse.ArgumentParser(description="NV GCB gaming collector (stub)")
    parser.add_argument("--scan-ids", action="store_true",
                        help="Scan recent document IDs to find Excel files (development only)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.scan_ids:
        print("Scanning NV GCB document IDs for Excel files (this takes ~2 min)...")
        for doc_id, url in _iter_recent_excel_ids():
            print(f"  Found Excel: docid={doc_id} {url}")
        return
    adapter = NVGamingAdapter()
    result = adapter.fetch()
    if result:
        for name, df in result.items():
            print(f"{name}: {len(df)} rows")
    else:
        print("STUB: no data returned (expected). See BACKFILL STRATEGY in source.")


if __name__ == "__main__":
    _cli()
