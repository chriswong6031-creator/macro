"""NY State Gaming Commission — weekly mobile-sports-wagering collector.

Source: https://www.gaming.ny.gov/gaming/index.php?sec=sports_mobile
Data: Weekly Excel workbooks published every Tuesday (covering the prior week
Mon-Sun).  First period available: April 4, 2022 (week ending 2022-04-10).

Schema history:
  v1 (2022-04-10 .. ~2023-06-11): columns in fixed order; operator names
      spelled differently across files (e.g. "BetMGM" vs "BET MGM").
  v2 (~2023-06-18 onward): standardized header row; "Gross Gaming Revenue"
      renamed "Gross Revenue from Mobile Sports Wagering".
  v3 (~2024-01+): aggregate "TOTAL" row sometimes appears/disappears; some
      workbooks have merged header cells.  The parser tolerates all three
      by normalizing the column search rather than relying on column position.

PIT contract: the release date is the publish date (Tuesday), not the period
end (Sunday).  Every row carries release_date (when we fetched), period_end
(Sunday of the covered week), and period_start (Monday).

Deseasonalization: NOT done here — the study (w4_gaming_tape_phase0.py) must
deseasonalize using YoY or seasonal-z per standing SEASONALITY law.

Nightly wiring (for consolidation):
  In scripts/collect.py (do NOT edit here):
    from collectors.gaming_ny import NYGamingAdapter
  In the nightly collector registry, add:
    NYGamingAdapter()
  Run:
    python -m collectors.gaming_ny --full-history  # backfill 2022-01->
    python -m collectors.gaming_ny                 # incremental
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
from lib import config, store  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
NY_INDEX_URL = (
    "https://www.gaming.ny.gov/gaming/index.php?sec=sports_mobile"
)
NY_DIRECT_BASE = (
    "https://www.gaming.ny.gov/pdf/sports/gaming-revenue/"
)

GROUP = "gaming_tape"
SERIES = "ny_weekly"
OUT_DIR_NAME = "ny_weekly"

# Operator name normalisation map (observed aliases -> canonical)
OPERATOR_ALIASES: dict[str, str] = {
    "bet mgm": "BETMGM",
    "betmgm": "BETMGM",
    "caesars": "CZRS",
    "caesars sportsbook": "CZRS",
    "draftkings": "DKNG",
    "draft kings": "DKNG",
    "fanduel": "FLUT_FD",
    "fanduel sportsbook": "FLUT_FD",
    "flutter / fanduel": "FLUT_FD",
    "penn": "PENN",
    "barstool": "PENN",
    "espn bet": "PENN",
    "penn interactive": "PENN",
    "pointsbet": "POINTSBET",
    "resorts world bet": "RWNY",
    "resorts world": "RWNY",
    "superbook": "SUPERBOOK",
    "winamax": "WINAMAX",
    "bet365": "BET365",
    "bally bet": "BALLY",
    "fanatics": "FANATICS",
    "hard rock bet": "HARDROCK",
}

REVENUE_COL_PATTERNS = [
    r"gross\s*gaming\s*revenue",
    r"gross\s*revenue",
    r"mobile\s*sports.*revenue",
    r"gsr",
    r"ggr",
]

HANDLE_COL_PATTERNS = [
    r"gross\s*wagers",
    r"total\s*wagers",
    r"wagers",
    r"handle",
]

HOLD_COL_PATTERNS = [
    r"hold\s*%",
    r"hold\s*percentage",
    r"hold",
]


def _norm_op(name: str) -> str:
    """Return canonical operator tag, or raw lower-stripped name if not mapped."""
    key = str(name).strip().lower()
    return OPERATOR_ALIASES.get(key, key.upper().replace(" ", "_"))


def _find_col(df: pd.DataFrame, patterns: list[str]) -> str | None:
    """Return first column name matching any pattern (case-insensitive)."""
    for pat in patterns:
        for col in df.columns:
            if re.search(pat, str(col), re.I):
                return col
    return None


def _parse_workbook(raw: bytes, period_end: date, release_date: date) -> pd.DataFrame:
    """Parse one NY Gaming Excel workbook into a tidy long frame.

    Returns columns: period_end, period_start, release_date, operator,
    handle_usd, revenue_usd, hold_pct.  Rows with no operator name are
    dropped (total/blank rows).

    Raises ValueError when the sheet cannot be parsed.
    """
    wb = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=None)

    # Find the header row: look for the row containing "operator" (case-insensitive)
    header_row_idx = None
    for idx, row in wb.iterrows():
        vals = [str(v).strip().lower() for v in row if pd.notna(v)]
        if any("operator" in v for v in vals):
            header_row_idx = idx
            break

    if header_row_idx is None:
        # Some older sheets lack an "operator" label; try first non-empty row
        for idx, row in wb.iterrows():
            vals = [str(v).strip() for v in row if pd.notna(v) and str(v).strip()]
            if len(vals) >= 3:
                header_row_idx = idx
                break

    if header_row_idx is None:
        raise ValueError("could not locate header row in workbook")

    df = wb.iloc[header_row_idx:].copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    # find operator column
    op_col = None
    for col in df.columns:
        if re.search(r"operator|licensee|company", col, re.I):
            op_col = col
            break
    if op_col is None:
        op_col = df.columns[0]  # first col by convention

    rev_col = _find_col(df, REVENUE_COL_PATTERNS)
    handle_col = _find_col(df, HANDLE_COL_PATTERNS)
    hold_col = _find_col(df, HOLD_COL_PATTERNS)

    if rev_col is None:
        raise ValueError(f"no revenue column found; cols={list(df.columns)}")

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
            s = str(v).replace(",", "").replace("$", "").replace("%", "").strip()
            try:
                return float(s) if s else None
            except ValueError:
                return None

        rev = _to_float(row.get(rev_col))
        handle = _to_float(row.get(handle_col)) if handle_col else None
        hold = _to_float(row.get(hold_col)) if hold_col else None

        rows.append({
            "period_end": period_end,
            "period_start": period_end - timedelta(days=6),
            "release_date": release_date,
            "operator": _norm_op(op_raw),
            "operator_raw": op_raw,
            "handle_usd": handle,
            "revenue_usd": rev,
            "hold_pct": hold,
        })

    if not rows:
        raise ValueError("no operator rows parsed")

    return pd.DataFrame(rows)


def _fetch_one(url: str, session: requests.Session, timeout: int = 30) -> bytes:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def _known_file_urls() -> list[tuple[date, str]]:
    """
    Build a list of (period_end, url) pairs by scraping the NY Gaming index page.
    The site publishes Excel files with names like:
      Mobile-Sports-Wagering-Revenue-Week-Ending-MMMDD-YYYY.xlsx
    We also try a direct pattern-constructed URL as a fallback.
    """
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://macro.mastermind-x.com)"
    )
    pairs: list[tuple[date, str]] = []
    try:
        r = session.get(NY_INDEX_URL, timeout=20)
        text = r.text
        # Find href links to xlsx
        for href in re.findall(r'href="([^"]*\.xlsx)"', text, re.I):
            # Try to parse the date from the filename
            m = re.search(
                r"week.ending.(\w+).(\d{1,2}).(\d{4})", href, re.I
            )
            if m:
                mon_str, day_str, year_str = m.groups()
                try:
                    dt = datetime.strptime(
                        f"{mon_str} {day_str} {year_str}", "%B %d %Y"
                    ).date()
                    full_url = href if href.startswith("http") else (
                        "https://www.gaming.ny.gov" + href
                    )
                    pairs.append((dt, full_url))
                except ValueError:
                    pass
    except Exception as exc:
        log.warning("NY index scrape failed: %s", exc)
    return sorted(set(pairs))


class NYGamingAdapter:
    """Standalone collector for NY Gaming Commission weekly mobile data."""

    name = "gaming_ny"
    group = GROUP
    stale_after_days = 9  # weekly release

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out_dir = config.data_dir() / GROUP / OUT_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = out_dir / "panel.parquet"

        existing = pd.read_parquet(parquet_path) if parquet_path.exists() else pd.DataFrame()
        existing_ends: set[date] = set()
        if not existing.empty and "period_end" in existing.columns:
            existing_ends = set(pd.to_datetime(existing["period_end"]).dt.date)

        pairs = _known_file_urls()
        if not pairs:
            log.warning("gaming_ny: no Excel links found; store unchanged")
            return {}

        today = date.today()
        frames: list[pd.DataFrame] = []
        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; MacroDashboard/1.0)"
        )

        fetched = 0
        for period_end, url in pairs:
            if period_end in existing_ends and not full_history:
                continue
            if period_end > today:
                continue
            # PIT: NY releases every Tuesday covering the prior Mon-Sun week.
            # release_date = the Tuesday immediately after period_end (Sunday + 2 days).
            # For the most-recent period still awaiting its real release, fall back
            # to fetch date only if the computed Tuesday is in the future.
            computed_release = period_end + timedelta(days=2)  # Sunday -> Tuesday
            release_date = computed_release if computed_release <= today else today
            try:
                raw = _fetch_one(url, session)
                df = _parse_workbook(raw, period_end, release_date=release_date)
                frames.append(df)
                fetched += 1
                log.info("gaming_ny: fetched %s (%d operators)", period_end, len(df))
                time.sleep(0.5)
            except Exception as exc:
                log.warning("gaming_ny: skipped %s — %s", period_end, exc)

        if not frames and existing.empty:
            log.info("gaming_ny: nothing fetched, store empty")
            return {}

        all_frames = []
        if not existing.empty:
            all_frames.append(existing)
        all_frames.extend(frames)

        panel = pd.concat(all_frames, ignore_index=True)
        panel["period_end"] = pd.to_datetime(panel["period_end"])
        panel = panel.drop_duplicates(
            subset=["period_end", "operator"], keep="last"
        ).sort_values(["period_end", "operator"]).reset_index(drop=True)
        panel.to_parquet(parquet_path, index=False)
        log.info("gaming_ny: saved %d rows (%d new periods)", len(panel), fetched)
        return {"ny_weekly": panel}

    def stored_series(self) -> list[str]:
        return ["ny_weekly"]

    def last_good_date(self) -> date | None:
        p = config.data_dir() / GROUP / OUT_DIR_NAME / "panel.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df.empty or "period_end" not in df.columns:
            return None
        return pd.to_datetime(df["period_end"]).max().date()


def _cli():
    parser = argparse.ArgumentParser(description="NY Gaming Commission weekly collector")
    parser.add_argument("--full-history", action="store_true",
                        help="Re-fetch all weeks (ignore existing)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    adapter = NYGamingAdapter()
    result = adapter.fetch(full_history=args.full_history)
    if result:
        for name, df in result.items():
            print(f"{name}: {len(df)} rows, periods {df['period_end'].min()} .. {df['period_end'].max()}")
    else:
        print("No data returned (network may be unavailable or no new periods)")


if __name__ == "__main__":
    _cli()
