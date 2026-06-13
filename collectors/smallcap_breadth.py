"""Small-cap internal breadth, computed from S&P SmallCap 600 constituents.

Identical machinery to collectors/breadth.py (S&P 500) — same Wikipedia table
shape (Symbol / Security / GICS Sector), same close-matrix download, same
% > 50/200DMA + NH/NL + A-D aggregates. Only the universe differs.

WHY the S&P 600 and not the literal Russell 2000: the true IWM holdings feed
(iShares) is Akamai-bot-blocked (see project notes / LIMITATIONS.md), and the
Russell 2000 has no free constituent list. The S&P SmallCap 600 is a clean,
free, well-defined small-cap index whose aggregate participation tracks the
Russell 2000 closely — the honest zero-cost proxy for small-cap breadth.

Outputs (data/smallcap_breadth/breadth.parquet): same columns as breadth.py.
"""
from __future__ import annotations

from collectors.breadth import BreadthAdapter
from lib import config


class SmallCapBreadthAdapter(BreadthAdapter):
    name = "smallcap_breadth"
    group = "smallcap_breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["smallcap_breadth"]
        self.ycfg = config.load()["yahoo"]
        self.cache_path = config.data_dir() / "smallcap_breadth" / "_closes_cache.parquet"

    def constituents_checked(self, members):
        # S&P 600 carries ~600 names; anything under 450 means the scrape broke
        if members.empty or len(members) < 450:
            raise ValueError(f"smallcap constituents list suspicious: {len(members)} rows")
        return members
