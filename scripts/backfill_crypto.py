"""One-time crypto history backfills (run locally, results live in git).

1. checkonchain.com SOPR 2011-07 -> today: parsed from the embedded Plotly JSON
   in their chart HTML. Seeds data/bgeo/sopr.parquet so the daily bgeo appends
   (2022->, free-tier window) extend an unbroken 15-year series, and archives
   the raw pull with provenance under data/archive/checkonchain/.
   Splice rule: bgeo wins on overlap (it upserts later; new wins on collision).
   Overlap diff stats are printed so the splice quality is on record.

Usage:
    python -m scripts.backfill_crypto [--only sopr]

Re-running is safe (upsert is idempotent). More checkonchain series can be
added to CHARTS as their URLs are verified.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_crypto")

# chart page -> (trace name in Plotly JSON, store group, series name, column)
CHARTS = {
    "sopr": {
        "url": "https://charts.checkonchain.com/btconchain/realised/sopr/sopr_light.html",
        "trace": "Spent Output Profit Ratio (SOPR)",
        "group": "bgeo",            # seeds/extends the live bgeo series
        "series": "sopr",
        "column": "sopr",
    },
}


def _decode_axis(v) -> pd.Series | pd.DatetimeIndex | list:
    """Plotly stores large arrays either as plain lists or as typed binary:
    {"dtype": "f8", "bdata": "<base64>"} — decode both."""
    if isinstance(v, dict) and "bdata" in v:
        import base64

        import numpy as np
        return np.frombuffer(base64.b64decode(v["bdata"]), dtype=v.get("dtype", "f8"))
    return v


def parse_plotly(html: str, trace_name: str) -> pd.DataFrame:
    m = re.search(r'Plotly\.newPlot\(\s*"[^"]+",\s*(\[.*?\])\s*,\s*\{', html, re.S)
    if not m:
        raise ValueError("no Plotly.newPlot payload found")
    traces = json.loads(m.group(1))
    for t in traces:
        if t.get("name") == trace_name:
            x, y = _decode_axis(t["x"]), _decode_axis(t["y"])
            df = pd.DataFrame({"date": pd.to_datetime(x),
                               "value": pd.to_numeric(y, errors="coerce")})
            return df.dropna().set_index("date")
    raise ValueError(f"trace {trace_name!r} not in {[t.get('name') for t in traces]}")


def backfill(key: str) -> None:
    spec = CHARTS[key]
    log.info("fetching %s", spec["url"])
    r = requests.get(spec["url"], timeout=120,
                     headers={"User-Agent": config.load()["sponsors"]["user_agent"]})
    r.raise_for_status()
    df = parse_plotly(r.text, spec["trace"]).rename(columns={"value": spec["column"]})
    df.index = df.index.normalize()
    log.info("%s: %d points, %s -> %s", key, len(df), df.index.min().date(), df.index.max().date())

    # archive raw pull with provenance
    adir = config.data_dir() / "archive" / "checkonchain"
    adir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(adir / f"{key}_full.parquet")
    meta = {"source": spec["url"], "trace": spec["trace"],
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "points": len(df), "first": str(df.index.min().date()),
            "last": str(df.index.max().date())}
    (adir / f"{key}_full.json").write_text(json.dumps(meta, indent=2))

    # splice-quality report vs whatever the live series already holds
    existing = store.read(spec["group"], spec["series"])
    if existing is not None and not existing.empty:
        both = existing.join(df, how="inner", rsuffix="_coc").dropna()
        if not both.empty:
            a, b = both.iloc[:, 0], both.iloc[:, 1]
            diff = (a - b).abs()
            log.info("overlap %d days: median |diff| %.5f, max %.5f (bgeo wins on collision)",
                     len(both), diff.median(), diff.max())

    # seed the live series — existing (bgeo) rows win on collision because
    # upsert favors... new frame. So: only insert rows NOT already stored.
    if existing is not None and not existing.empty:
        df = df[~df.index.isin(existing.index)]
    if df.empty:
        log.info("%s: nothing new to seed (already covered)", key)
        return
    store.upsert(spec["group"], spec["series"], df)
    log.info("%s: seeded %d historical rows into data/%s/%s.parquet",
             key, len(df), spec["group"], spec["series"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    keys = [k.strip() for k in args.only.split(",") if k.strip()] or list(CHARTS)
    for k in keys:
        backfill(k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
