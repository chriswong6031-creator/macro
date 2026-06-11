"""Second Wayback tactic for FRED series with no archived fredgraph.csv:
captures of the fred.stlouisfed.org/data/<SID> HTML page embed the full
observation table (captures before ~2025; later ones are paginated to 1000
rows and rejected by the row-count guard).

Usage: python -m scripts.fred_datapage_fallback SID [SID...]
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "macro-dashboard/1.0 (research; archived-data fallback)"}
ROW_RE = re.compile(
    r'<th scope="row"[^>]*>(\d{4}-\d{2}-\d{2})</th>\s*<td[^>]*>\s*([\d.\-]+)\s*</td>')


def captures(sid: str) -> list[str]:
    for attempt in range(3):
        try:
            r = requests.get(CDX, params={"url": f"fred.stlouisfed.org/data/{sid}",
                                          "output": "json", "filter": "statuscode:200",
                                          "collapse": "timestamp:6"},
                             headers=UA, timeout=60)
            r.raise_for_status()
            rows = r.json()
            return [x[1] for x in rows[1:]][::-1]  # newest first
        except Exception as e:  # noqa: BLE001
            print(f"  cdx retry {attempt + 1}: {e}")
            time.sleep(5 * (attempt + 1))
    return []


def fetch(sid: str, ts: str) -> pd.DataFrame | None:
    url = f"https://web.archive.org/web/{ts}id_/https://fred.stlouisfed.org/data/{sid}"
    try:
        r = requests.get(url, headers=UA, timeout=120)
        r.raise_for_status()
        rows = ROW_RE.findall(r.text)
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", sid])
        df[sid] = pd.to_numeric(df[sid], errors="coerce")
        df = df.dropna().set_index("date")
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:  # noqa: BLE001
        print(f"  {ts}: {e}")
        return None


def col_name(sid: str) -> str:
    for grp in config.load()["fred"]["series"].values():
        if sid in grp:
            return grp[sid]
    return sid.lower()


def main() -> None:
    sids = sys.argv[1:]
    for sid in sids:
        print(f"=== {sid} ===")
        best: pd.DataFrame | None = None
        for ts in captures(sid)[:12]:
            df = fetch(sid, ts)
            if df is None:
                continue
            print(f"  {ts[:8]}: {len(df)} rows {df.index.min().date()}..{df.index.max().date()}")
            if best is None or len(df) > len(best):
                best = df
            if len(df) > 2500:   # clearly a full (non-paginated) daily table
                break
            time.sleep(1)
        if best is None or len(best) < 200:
            print(f"  -> NOTHING USABLE for {sid}")
            continue
        best.columns = [col_name(sid)]
        store.upsert("fred", sid, best, outlier_col=best.columns[0])
        print(f"  -> stored {len(best)} rows as fred/{sid}")


if __name__ == "__main__":
    main()
