"""Seed the per-name CN + HK OHLC stores for a curated handful of liquid names, so
the new collector (collectors/china_stock_prices.py + collectors/hk_stock_prices.py)
is proven end-to-end and the committed store is real & verifiable. The full ~1.5k CN
+ ~160 HK search universe backfills via the nightly run
(``python -m scripts.collect --only china_stocks,hk_stocks``) — ``store.upsert`` is
incremental, so seeded names just take the cheap 1mo window thereafter.

Run:  python -m scripts.seed_cn_hk_stocks
"""
from __future__ import annotations

import logging

from collectors.china_stock_prices import ChinaStockPriceAdapter
from collectors.hk_stock_prices import HkStockPriceAdapter
from lib import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_cn_hk")


def _seed(adapter) -> int:
    seed = adapter.cfg.get("seed", [])
    if not seed:
        log.warning("%s: no seed configured", adapter.group)
        return 0
    log.info("%s: seeding %d names (full history)...", adapter.group, len(seed))
    frames = adapter.fetch(full_history=True, tickers=seed)
    n = 0
    for name, df in sorted(frames.items()):
        df = adapter.validate(name, df)
        merged = store.upsert(adapter.group, name, df)
        log.info("  %-12s %5d rows  %s -> %s  cols=%s", name, len(merged),
                 merged.index.min().date(), merged.index.max().date(), list(merged.columns))
        n += 1
    missing = [t for t in seed if t not in frames]
    if missing:
        log.warning("%s: no data for %s", adapter.group, missing)
    return n


def main() -> None:
    cn = _seed(ChinaStockPriceAdapter())
    hk = _seed(HkStockPriceAdapter())
    log.info("seeded %d china_stocks + %d hk_stocks parquets", cn, hk)


if __name__ == "__main__":
    main()
