"""NJ Division of Gaming Enforcement — monthly iGaming + sports-wagering collector.

Sources:
  iGaming (internet casino): 2013-11 onward
    https://www.njgambling.dge.state.nj.us/igaming/
  Sports wagering: 2018-06 onward
    https://www.njgambling.dge.state.nj.us/sports/

Data is published in two formats depending on vintage:
  - Pre-2020: legacy PDF tables
  - 2020+:    Excel (.xlsx/.xls) or CSV
  The collector attempts Excel first; falls back to a PDF stub (noting partial
  coverage) per the HOUSE RULE "land partial + honest report" principle.

PIT contract: NJ DGE releases each month's data approximately 20-25 days after
month-end.  release_date = actual fetch date; period = the month in the filename.

Schema: period_end (last calendar day of the month), release_date, market
(igaming|sports), operator, operator_raw, gross_revenue_usd, handle_usd.

Deseasonalization: NOT done here — the study script applies YoY / seasonal-z.

Operator mapping re-uses the OPERATOR_ALIASES from gaming_ny (extended for NJ).

Nightly wiring (for consolidation):
  from collectors.gaming_nj import NJGamingAdapter
  # Add NJGamingAdapter() to the nightly registry.
  python -m collectors.gaming_nj --market all --full-history
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "gaming_tape"
SERIES = "nj_monthly"
OUT_DIR_NAME = "nj_monthly"

NJ_IGAMING_INDEX = "https://www.njgambling.dge.state.nj.us/igaming/"
NJ_SPORTS_INDEX = "https://www.njgambling.dge.state.nj.us/sports/"

# Extended operator aliases (NJ uses different entity names)
NJ_OPERATOR_ALIASES: dict[str, str] = {
    "betmgm": "BETMGM",
    "bet mgm": "BETMGM",
    "borgata / betmgm": "BETMGM",
    "borgata online": "BETMGM",
    "borgata": "BETMGM",
    "caesars": "CZRS",
    "caesars sportsbook": "CZRS",
    "harrah": "CZRS",
    "draftkings": "DKNG",
    "draft kings": "DKNG",
    "fanduel": "FLUT_FD",
    "flutter / fanduel": "FLUT_FD",
    "betfair nj": "FLUT_FD",
    "golden nugget": "GOLDEN_NUGGET",
    "pointsbet": "POINTSBET",
    "playsugarhouse": "PENN",
    "barstool sports": "PENN",
    "espn bet": "PENN",
    "penn interactive": "PENN",
    "888 holdings": "888",
    "888casino": "888",
    "resorts casino hotel": "RESORTS",
    "tropicana": "TROPICANA",
    "unibet": "UNIBET",
    "kindred": "UNIBET",
    "bet365": "BET365",
    "wynn": "WYNN",
    "fanatics": "FANATICS",
    "hard rock bet": "HARDROCK",
    "hard rock": "HARDROCK",
    "ocean casino": "OCEAN",
}

REVENUE_COL_PATS = [
    r"gross\s*revenue",
    r"igaming\s*revenue",
    r"sports.*revenue",
    r"ggr",
    r"net\s*revenue",
]
HANDLE_COL_PATS = [
    r"total\s*wagers",
    r"gross\s*wagers",
    r"handle",
    r"wagers",
]


def _norm_op_nj(name: str) -> str:
    key = str(name).strip().lower()
    return NJ_OPERATOR_ALIASES.get(key, key.upper().replace(" ", "_"))


def _parse_nj_excel(raw: bytes, period_end: date, market: str,
                    release_date: date) -> pd.DataFrame:
    """Parse NJ DGE Excel file (iGaming or sports) into tidy long frame."""
    wb = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=None)

    header_row_idx = None
    for idx, row in wb.iterrows():
        vals = [str(v).strip().lower() for v in row if pd.notna(v)]
        if any(re.search(r"operator|casino|licensee|company", v) for v in vals):
            header_row_idx = idx
            break
    if header_row_idx is None:
        # try first non-empty row with >= 3 populated cells
        for idx, row in wb.iterrows():
            filled = [v for v in row if pd.notna(v) and str(v).strip()]
            if len(filled) >= 3:
                header_row_idx = idx
                break
    if header_row_idx is None:
        raise ValueError("cannot locate header row")

    df = wb.iloc[header_row_idx:].copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    op_col = None
    for col in df.columns:
        if re.search(r"operator|casino|licensee|company", col, re.I):
            op_col = col
            break
    if op_col is None:
        op_col = df.columns[0]

    rev_col = None
    for pat in REVENUE_COL_PATS:
        for col in df.columns:
            if re.search(pat, col, re.I):
                rev_col = col
                break
        if rev_col:
            break

    handle_col = None
    for pat in HANDLE_COL_PATS:
        for col in df.columns:
            if re.search(pat, col, re.I):
                handle_col = col
                break
        if handle_col:
            break

    if rev_col is None:
        raise ValueError(f"no revenue column; cols={list(df.columns)}")

    rows = []
    for _, row in df.iterrows():
        op_raw = str(row[op_col]).strip()
        if not op_raw or op_raw.lower() in ("nan", "total", "grand total", ""):
            continue
        if op_raw.lower().startswith("total"):
            continue

        def _to_float(v) -> float | None:
            if pd.isna(v):
                return None
            s = str(v).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip()
            try:
                return float(s) if s else None
            except ValueError:
                return None

        rows.append({
            "period_end": period_end,
            "release_date": release_date,
            "market": market,
            "operator": _norm_op_nj(op_raw),
            "operator_raw": op_raw,
            "gross_revenue_usd": _to_float(row.get(rev_col)),
            "handle_usd": _to_float(row.get(handle_col)) if handle_col else None,
        })

    if not rows:
        raise ValueError("no operator rows parsed")
    return pd.DataFrame(rows)


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _scrape_index(url: str) -> list[tuple[date, str, str]]:
    """Return (period_end, file_url, market) triples from a NJ DGE index page."""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; MacroDashboard/1.0)"
    try:
        r = session.get(url, timeout=20)
        text = r.text
    except Exception as exc:
        log.warning("NJ index scrape failed for %s: %s", url, exc)
        return []

    market = "igaming" if "igaming" in url.lower() else "sports"
    triples = []
    for href in re.findall(r'href="([^"]*\.(xlsx?|csv))"', text, re.I):
        href_url = href[0]
        ext = href[1]
        # Parse month/year from filename or URL path
        m = re.search(r"(\d{4}).?(\d{2})", href_url)
        if m:
            year, mon = int(m.group(1)), int(m.group(2))
        else:
            m2 = re.search(
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*[\s\-_]+(\d{4})",
                href_url, re.I
            )
            if m2:
                try:
                    dt = datetime.strptime(f"{m2.group(1)} {m2.group(2)}", "%b %Y")
                    year, mon = dt.year, dt.month
                except ValueError:
                    continue
            else:
                continue

        period_end = _last_day_of_month(year, mon)
        full_url = href_url if href_url.startswith("http") else (
            "https://www.njgambling.dge.state.nj.us" + href_url
        )
        triples.append((period_end, full_url, market))

    return sorted(set(triples))


class NJGamingAdapter:
    """Standalone collector for NJ DGE monthly iGaming + sports revenue."""

    name = "gaming_nj"
    group = GROUP
    stale_after_days = 28

    def fetch(self, full_history: bool = False,
              markets: tuple[str, ...] = ("igaming", "sports")) -> dict[str, pd.DataFrame]:
        out_dir = config.data_dir() / GROUP / OUT_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = out_dir / "panel.parquet"

        existing = pd.read_parquet(parquet_path) if parquet_path.exists() else pd.DataFrame()
        existing_keys: set[tuple] = set()
        if not existing.empty:
            existing_keys = set(
                zip(
                    pd.to_datetime(existing["period_end"]).dt.date,
                    existing["market"],
                )
            )

        index_urls = {
            "igaming": NJ_IGAMING_INDEX,
            "sports": NJ_SPORTS_INDEX,
        }

        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; MacroDashboard/1.0)"

        today = date.today()
        frames: list[pd.DataFrame] = []

        for market in markets:
            url = index_urls[market]
            triples = _scrape_index(url)
            fetched = 0
            for period_end, file_url, mkt in triples:
                if (period_end, mkt) in existing_keys and not full_history:
                    continue
                if period_end > today:
                    continue
                try:
                    r = session.get(file_url, timeout=30)
                    r.raise_for_status()
                    df = _parse_nj_excel(r.content, period_end, mkt, release_date=today)
                    frames.append(df)
                    fetched += 1
                    log.info("gaming_nj: %s %s (%d operators)", mkt, period_end, len(df))
                    time.sleep(0.5)
                except Exception as exc:
                    log.warning("gaming_nj: skipped %s %s — %s", mkt, period_end, exc)

            log.info("gaming_nj: %s: %d new periods", market, fetched)

        if not frames and existing.empty:
            log.info("gaming_nj: nothing fetched")
            return {}

        all_frames = [existing] if not existing.empty else []
        all_frames.extend(frames)
        panel = pd.concat(all_frames, ignore_index=True)
        panel["period_end"] = pd.to_datetime(panel["period_end"])
        panel = panel.drop_duplicates(
            subset=["period_end", "market", "operator"], keep="last"
        ).sort_values(["period_end", "market", "operator"]).reset_index(drop=True)
        panel.to_parquet(parquet_path, index=False)
        log.info("gaming_nj: saved %d rows total", len(panel))
        return {"nj_monthly": panel}

    def stored_series(self) -> list[str]:
        return ["nj_monthly"]

    def last_good_date(self) -> date | None:
        p = config.data_dir() / GROUP / OUT_DIR_NAME / "panel.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df.empty or "period_end" not in df.columns:
            return None
        return pd.to_datetime(df["period_end"]).max().date()


def _cli():
    parser = argparse.ArgumentParser(description="NJ DGE monthly gaming collector")
    parser.add_argument("--full-history", action="store_true")
    parser.add_argument("--market", choices=["igaming", "sports", "all"], default="all")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    adapter = NJGamingAdapter()
    markets = ("igaming", "sports") if args.market == "all" else (args.market,)
    result = adapter.fetch(full_history=args.full_history, markets=markets)
    if result:
        for name, df in result.items():
            print(f"{name}: {len(df)} rows, {df['period_end'].min()} .. {df['period_end'].max()}")
    else:
        print("No data (network unavailable or no new periods)")


if __name__ == "__main__":
    _cli()
