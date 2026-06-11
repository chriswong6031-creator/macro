"""One-time fetch of archived pre-truncation OAS history (FRED now serves a
rolling 3-year window for ICE BofA series). Sources are Wayback Machine
captures of FRED's own endpoints — provenance recorded in
data/archive/PROVENANCE.md and DECISIONS.md.

Usage: python -m scripts.fetch_archive
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

HYM2_URL = ("https://web.archive.org/web/20251104204105id_/"
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2")
CM_URL = ("https://web.archive.org/web/20241027011157id_/"
          "https://fred.stlouisfed.org/data/BAMLC0A0CM")

PROVENANCE = """# Archived OAS history — provenance

FRED serves only a rolling 3-year window for ICE BofA OAS series since
April 2026. The files here restore full history for classifier validation.

| file | series | range | source |
|---|---|---|---|
| BAMLH0A0HYM2.parquet | ICE BofA US High Yield OAS | 1996-12-31 .. 2025-11-03 | Wayback capture 2025-11-04 of fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 |
| BAMLC0A0CM.parquet | ICE BofA US Corporate OAS | 1996-12-31 .. 2024-10-24 | Wayback capture 2024-10-27 of fred.stlouisfed.org/data/BAMLC0A0CM (HTML table) |

Spot-checks at storage time (exact): HY 2008-12-15 = 21.82, 2020-03-23 = 10.87,
2021-06-15 = 3.17. IG 2008-12-15 = 6.51, 2020-03-23 = 4.01.
Publisher of underlying data: Federal Reserve Bank of St. Louis / ICE Data Indices.
Live observations (2023+) are merged from the ongoing FRED collector, whose
store is append-only — nothing fetched is ever dropped.
"""


def fetch_hym2(dest: Path) -> pd.DataFrame:
    r = requests.get(HYM2_URL, timeout=120, headers={"User-Agent": "macro-dashboard/1.0"})
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "hy_oas"]
    df["hy_oas"] = pd.to_numeric(df["hy_oas"], errors="coerce")
    df = df.dropna().set_index("date")
    df.index = pd.to_datetime(df.index)
    df.to_parquet(dest / "BAMLH0A0HYM2.parquet")
    return df


def fetch_cm(dest: Path) -> pd.DataFrame:
    r = requests.get(CM_URL, timeout=180, headers={"User-Agent": "macro-dashboard/1.0"})
    r.raise_for_status()
    rows = re.findall(
        r'<th scope="row"[^>]*>(\d{4}-\d{2}-\d{2})</th>\s*<td[^>]*>\s*([\d.]+)\s*</td>',
        r.text)
    df = pd.DataFrame(rows, columns=["date", "ig_oas"])
    df["ig_oas"] = pd.to_numeric(df["ig_oas"], errors="coerce")
    df = df.dropna().set_index("date")
    df.index = pd.to_datetime(df.index)
    df.to_parquet(dest / "BAMLC0A0CM.parquet")
    return df


def main() -> None:
    dest = config.ROOT / config.load()["storage"]["archive_dir"]
    dest.mkdir(parents=True, exist_ok=True)

    hy = fetch_hym2(dest)
    assert abs(hy.loc["2008-12-15", "hy_oas"] - 21.82) < 0.01, "HY 2008 spot-check failed"
    assert abs(hy.loc["2020-03-23", "hy_oas"] - 10.87) < 0.01, "HY 2020 spot-check failed"
    print(f"HY OAS: {len(hy)} rows {hy.index.min().date()} -> {hy.index.max().date()}")

    ig = fetch_cm(dest)
    assert abs(ig.loc["2020-03-23", "ig_oas"] - 4.01) < 0.01, "IG 2020 spot-check failed"
    print(f"IG OAS: {len(ig)} rows {ig.index.min().date()} -> {ig.index.max().date()}")

    (dest / "PROVENANCE.md").write_text(PROVENANCE)
    print("provenance written")


if __name__ == "__main__":
    main()
