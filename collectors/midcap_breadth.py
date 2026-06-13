"""Mid-cap internal breadth + constituent close matrix, from the S&P MidCap 400.

Third BreadthAdapter subclass (after S&P 500 breadth.py and S&P 600
smallcap_breadth.py) — same Wikipedia table shape (Symbol / Security / GICS
Sector), same close-matrix download/cache, same aggregates. It completes the
S&P Composite 1500 size spectrum (large + mid + small) that feeds the
searchable stock library.

Outputs (data/midcap_breadth/): breadth.parquet (aggregates) +
_closes_cache.parquet (the wide constituent close matrix the stock library
reads) + constituents.parquet (symbol -> name/sector reference).
"""
from __future__ import annotations

from collectors.breadth import BreadthAdapter
from lib import config


class MidCap400BreadthAdapter(BreadthAdapter):
    name = "midcap_breadth"
    group = "midcap_breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["midcap_breadth"]
        self.ycfg = config.load()["yahoo"]
        self.cache_path = config.data_dir() / "midcap_breadth" / "_closes_cache.parquet"

    def constituents_checked(self, members):
        # S&P 400 carries ~400 names; anything under 350 means the scrape broke
        if members.empty or len(members) < 350:
            raise ValueError(f"midcap constituents list suspicious: {len(members)} rows")
        return members
