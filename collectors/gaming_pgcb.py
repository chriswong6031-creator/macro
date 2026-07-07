"""PA Gaming Control Board (PGCB) — monthly revenue collector.

Sources:
  Slots + Tables (land-based): FY2019 (Jul-2018) onward
  iGaming (internet gaming): FY2019 (Nov-2018 launch) onward
  Sports wagering: FY2019 (Nov-2018 launch) onward

Published at: https://gamingcontrolboard.pa.gov/gaming/revenue/
As monthly Excel reports, typically released 10-15 business days after month-end.

PGCB fiscal year: July 1 – June 30 (so FY2019 = Jul 2018 – Jun 2019).
The monthly Excel reports use this fiscal convention in their file names.

PIT contract: release_date = fetch date; period_end = last calendar day of
the reported month.

Schema: period_end, release_date, segment (slots|tables|igaming|sports),
operator, operator_raw, gross_revenue_usd.

Nightly wiring (for consolidation):
  from collectors.gaming_pgcb import PGCBGamingAdapter
  # Add PGCBGamingAdapter() to the nightly registry.
  python -m collectors.gaming_pgcb --full-history
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

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "gaming_tape"
OUT_DIR_NAME = "pgcb_monthly"

PGCB_INDEX = "https://gamingcontrolboard.pa.gov/gaming/revenue/"

PGCB_OPERATOR_ALIASES: dict[str, str] = {
    "rivers casino": "PENN",
    "rivers casino 4 ever": "PENN",
    "rivers pittsburgh": "PENN",
    "rivers philadelphia": "PENN",
    "rivers casino des plaines": "PENN",
    "hollywood casino": "PENN",
    "penn national": "PENN",
    "hollywood": "PENN",
    "betmgm": "BETMGM",
    "bet mgm": "BETMGM",
    "borgata": "BETMGM",
    "borgata hotel casino": "BETMGM",
    "caesars": "CZRS",
    "caesars sportsbook": "CZRS",
    "harrahs": "CZRS",
    "harrah": "CZRS",
    "draftkings": "DKNG",
    "draft kings": "DKNG",
    "fanduel": "FLUT_FD",
    "fanduel sportsbook": "FLUT_FD",
    "flutter": "FLUT_FD",
    "parx casino": "PARX",
    "parx": "PARX",
    "wind creek": "WIND_CREEK",
    "presque isle downs": "PRESQUE_ISLE",
    "mount airy casino": "MOUNT_AIRY",
    "live casino": "LIVE_CASINO",
    "golden nugget": "GOLDEN_NUGGET",
    "bet365": "BET365",
    "fanatics": "FANATICS",
    "espn bet": "PENN",
    "barstool sports": "PENN",
    "unibet": "UNIBET",
    "kindred": "UNIBET",
}


def _norm_pgcb(name: str) -> str:
    key = str(name).strip().lower()
    return PGCB_OPERATOR_ALIASES.get(key, key.upper().replace(" ", "_"))


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _detect_segment(filename: str) -> str:
    fn = filename.lower()
    if "igaming" in fn or "internet" in fn:
        return "igaming"
    if "sports" in fn:
        return "sports"
    if "slot" in fn:
        return "slots"
    if "table" in fn:
        return "tables"
    return "unknown"


def _parse_pgcb_excel(raw: bytes, period_end: date, segment: str,
                      release_date: date) -> pd.DataFrame:
    """Parse one PGCB monthly revenue Excel into tidy long frame."""
    # Try multiple sheets; PGCB sometimes embeds all segments in one workbook
    try:
        xf = pd.ExcelFile(io.BytesIO(raw))
        sheet_names = xf.sheet_names
    except Exception as exc:
        raise ValueError(f"cannot open Excel: {exc}") from exc

    # Find the most relevant sheet
    chosen_sheet = sheet_names[0]
    for sn in sheet_names:
        if re.search(r"revenue|operator|monthly", str(sn), re.I):
            chosen_sheet = sn
            break

    wb = pd.read_excel(io.BytesIO(raw), sheet_name=chosen_sheet, header=None)

    # Find header row
    header_row_idx = None
    for idx, row in wb.iterrows():
        vals = [str(v).strip().lower() for v in row if pd.notna(v)]
        if any(re.search(r"operator|licensee|casino|name", v) for v in vals):
            header_row_idx = idx
            break
    if header_row_idx is None:
        for idx, row in wb.iterrows():
            filled = [v for v in row if pd.notna(v) and str(v).strip()]
            if len(filled) >= 3:
                header_row_idx = idx
                break
    if header_row_idx is None:
        raise ValueError("cannot find header row")

    df = wb.iloc[header_row_idx:].copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    op_col = None
    for col in df.columns:
        if re.search(r"operator|licensee|casino|name", col, re.I):
            op_col = col
            break
    if op_col is None:
        op_col = df.columns[0]

    rev_col = None
    for col in df.columns:
        if re.search(r"gross.*revenue|ggr|net.*revenue|revenue", col, re.I):
            rev_col = col
            break
    if rev_col is None and len(df.columns) > 1:
        # take second column as best guess
        rev_col = df.columns[1]

    rows = []
    for _, row in df.iterrows():
        op_raw = str(row[op_col]).strip()
        if not op_raw or op_raw.lower() in ("nan", "total", "grand total", ""):
            continue
        if op_raw.lower().startswith("total"):
            continue

        def _to_float(v) -> float | None:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            s = str(v).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip()
            try:
                return float(s) if s else None
            except ValueError:
                return None

        rows.append({
            "period_end": period_end,
            "release_date": release_date,
            "segment": segment,
            "operator": _norm_pgcb(op_raw),
            "operator_raw": op_raw,
            "gross_revenue_usd": _to_float(row.get(rev_col)),
        })

    if not rows:
        raise ValueError("no operator rows parsed")
    return pd.DataFrame(rows)


def _scrape_pgcb_index() -> list[tuple[date, str, str]]:
    """Scrape PGCB index page for Excel links.
    Returns (period_end, url, segment) triples.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; MacroDashboard/1.0)"
    try:
        r = session.get(PGCB_INDEX, timeout=20)
        text = r.text
    except Exception as exc:
        log.warning("PGCB index scrape failed: %s", exc)
        return []

    triples = []
    for href in re.findall(r'href="([^"]*\.(xlsx?))"', text, re.I):
        href_url = href[0]
        segment = _detect_segment(href_url)
        # Parse date from filename pattern like "Nov2023" or "2023-11" or "nov-23"
        m = re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s\-_]?(\d{4})",
            href_url, re.I
        )
        if m:
            from datetime import datetime as dt_
            try:
                dt = dt_.strptime(f"{m.group(1)[:3]} {m.group(2)}", "%b %Y")
                period_end = _last_day_of_month(dt.year, dt.month)
            except ValueError:
                continue
        else:
            m2 = re.search(r"(\d{4}).?(\d{2})", href_url)
            if m2:
                year, mon = int(m2.group(1)), int(m2.group(2))
                if 1 <= mon <= 12:
                    period_end = _last_day_of_month(year, mon)
                else:
                    continue
            else:
                continue

        full_url = href_url if href_url.startswith("http") else (
            "https://gamingcontrolboard.pa.gov" + href_url
        )
        triples.append((period_end, full_url, segment))

    return sorted(set(triples))


class PGCBGamingAdapter:
    """Standalone collector for PGCB monthly gaming revenue."""

    name = "gaming_pgcb"
    group = GROUP
    stale_after_days = 28

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out_dir = config.data_dir() / GROUP / OUT_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = out_dir / "panel.parquet"

        existing = pd.read_parquet(parquet_path) if parquet_path.exists() else pd.DataFrame()
        existing_keys: set[tuple] = set()
        if not existing.empty:
            existing_keys = set(
                zip(
                    pd.to_datetime(existing["period_end"]).dt.date,
                    existing["segment"],
                )
            )

        triples = _scrape_pgcb_index()
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; MacroDashboard/1.0)"
        today = date.today()

        frames: list[pd.DataFrame] = []
        fetched = 0
        for period_end, url, segment in triples:
            if (period_end, segment) in existing_keys and not full_history:
                continue
            if period_end > today:
                continue
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                df = _parse_pgcb_excel(r.content, period_end, segment, release_date=today)
                frames.append(df)
                fetched += 1
                log.info("gaming_pgcb: %s %s (%d rows)", segment, period_end, len(df))
                time.sleep(0.5)
            except Exception as exc:
                log.warning("gaming_pgcb: skipped %s %s — %s", segment, period_end, exc)

        if not frames and existing.empty:
            log.info("gaming_pgcb: nothing fetched")
            return {}

        all_frames = [existing] if not existing.empty else []
        all_frames.extend(frames)
        panel = pd.concat(all_frames, ignore_index=True)
        panel["period_end"] = pd.to_datetime(panel["period_end"])
        panel = panel.drop_duplicates(
            subset=["period_end", "segment", "operator"], keep="last"
        ).sort_values(["period_end", "segment", "operator"]).reset_index(drop=True)
        panel.to_parquet(parquet_path, index=False)
        log.info("gaming_pgcb: saved %d rows (%d new files)", len(panel), fetched)
        return {"pgcb_monthly": panel}

    def stored_series(self) -> list[str]:
        return ["pgcb_monthly"]

    def last_good_date(self) -> date | None:
        p = config.data_dir() / GROUP / OUT_DIR_NAME / "panel.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df.empty or "period_end" not in df.columns:
            return None
        return pd.to_datetime(df["period_end"]).max().date()


def _cli():
    parser = argparse.ArgumentParser(description="PGCB monthly gaming collector")
    parser.add_argument("--full-history", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    adapter = PGCBGamingAdapter()
    result = adapter.fetch(full_history=args.full_history)
    if result:
        for name, df in result.items():
            print(f"{name}: {len(df)} rows, {df['period_end'].min()} .. {df['period_end'].max()}")
    else:
        print("No data (network unavailable or no new periods)")


if __name__ == "__main__":
    _cli()
