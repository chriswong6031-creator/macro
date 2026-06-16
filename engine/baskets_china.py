"""China thematic baskets — the A-share analogue of engine.baskets.

Equal-weight, point-in-time dated-membership trackers over the FREE china_search cache
(top-market-cap A-shares, ~5y), benchmarked to the CSI 300 (沪深300, the 510300.SS ETF).
Mirrors engine.baskets.compute_baskets() exactly — and reuses its level/return/perf math
(_ew_level / _mtd_anchor / _perf) so the two pages are computed identically — but swaps the
data plane to China:

  • member closes      → data/china_search/closes.parquet  (wide [Date × ticker])
  • member display name → membership.json `name_zh` (the canonical A-share name)
  • benchmark           → store.read("china", "510300.SS")  (CSI 300 ETF)
  • etf_proxy cross-check → the china-group sector ETFs (半导体/酒/银行/证券…)

Emits the same two payloads the page renders client-side:
  CHART   = { dates:[ISO], bench:[CSI300 level], baskets:{id:[EW level series]} }
  BASKETS = { as_of, benchmark_label{,_zh}, construction, history_note, note, categories,
              categories_zh, story, baskets:[ {id,name,name_zh,category,category_zh,thesis,
              thesis_zh,weighting,created,n_members,members:[…], changelog, reference,
              missing, partial, perf} ] }

HONEST BY CONSTRUCTION (house rule): membership.json is curated with knowledge of the
period, so the series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest
and not a buy list. Additive — any failure returns None and the page is skipped.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.baskets_region import compute_region_baskets
from lib import config, store

log = logging.getLogger(__name__)

BENCHMARK_DEFAULT = "510300.SS"   # CSI 300 ETF (沪深300)


def _membership() -> dict | None:
    p = config.data_dir() / "baskets_china" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("china baskets membership unreadable: %s", e)
        return None


def _closes() -> pd.DataFrame | None:
    """Wide [Date × ticker] adjusted closes for the china_search universe (~800 names, ~5y)."""
    p = config.data_dir() / "china_search" / "closes.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("china_search closes unreadable: %s", e)
        return None


def compute_china_baskets() -> dict | None:
    """Load the China data plane (china_search closes + CSI 300 ETF benchmark + china-group
    sector-ETF proxies) and delegate the equal-weight/perf compute to engine.baskets_region.
    Member display name = the canonical A-share `name_zh`. The loaders above stay here so the
    tests can monkeypatch them."""
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    bench = store.read("china", mem.get("benchmark", BENCHMARK_DEFAULT))
    return compute_region_baskets(closes, mem, bench,
                                  lambda s: store.read("china", s), name_key="name_zh")
