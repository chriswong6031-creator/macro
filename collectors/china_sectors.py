"""China Shenwan (申万) L1 industry indices — the authoritative domestic sector
index family and the free analogue of the Bloomberg GS China sector baskets
(GSXACHBA banks / GSXACCON consumption / GSXACNRE real estate / GSXACNAU auto).

Mainland institutional desks watch the Shenwan L1 indices the way an offshore desk
watches the GS baskets. They are *real* sector indices (not ETF proxies), with deep
history — most L1 industries print from 1999-12-31, the 2014-reindexed ones (banks,
auto, non-bank financials …) from 2014-02-21 — which is what makes a tops/bottoms
study and a cycle calibration possible (the sector ETFs only go back ~5y).

Source: akshare, keyless.
  • `index_hist_sw(symbol=code, period="day")` — daily index OHLC + volume + amount,
    full history every call (so store.upsert is idempotent).
  • `sw_index_first_info()` — current static-PE / TTM-PE / PB / dividend-yield per L1
    industry, appended one row/day so the engine can percentile-rank a sector's
    valuation against its own accruing history.

Stored under group `china_sectors`: one parquet per L1 code (e.g. `801780.parquet` =
银行/Banks) with close/open/high/low/volume/amount, plus `valuation.parquet` (wide,
one row/day: `<code>_pe_ttm` / `<code>_pb` / `<code>_div`).

Akshare segfaults under threads → registered as a SERIAL collector in scripts/collect.py
(deliberately NOT in `_CONCURRENT_HOSTS`). Per-code isolation: one dead industry logs a
gap and the rest of the board still updates.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

# Shenwan L1 industry universe (31 codes, stable). code -> (cn, en). Hardcoded so a
# flaky `sw_index_first_info` never strands the price collection; the valuation pass
# refreshes display PE/PB/div on top. engine/china_sectors.py maps dashboard sectors
# (and the GS consumption composite) onto these codes via config.china.shenwan.
SW_L1: dict[str, tuple[str, str]] = {
    "801010": ("农林牧渔", "Agriculture"),
    "801030": ("基础化工", "Chemicals"),
    "801040": ("钢铁", "Steel"),
    "801050": ("有色金属", "Nonferrous Metals"),
    "801080": ("电子", "Electronics"),
    "801110": ("家用电器", "Home Appliances"),
    "801120": ("食品饮料", "Food & Beverage"),
    "801130": ("纺织服饰", "Textiles & Apparel"),
    "801140": ("轻工制造", "Light Manufacturing"),
    "801150": ("医药生物", "Pharma & Biotech"),
    "801160": ("公用事业", "Utilities"),
    "801170": ("交通运输", "Transportation"),
    "801180": ("房地产", "Real Estate"),
    "801200": ("商贸零售", "Retail & Commerce"),
    "801210": ("社会服务", "Consumer Services"),
    "801230": ("综合", "Conglomerates"),
    "801710": ("建筑材料", "Building Materials"),
    "801720": ("建筑装饰", "Construction"),
    "801730": ("电力设备", "Power Equipment"),
    "801740": ("国防军工", "Defense & Military"),
    "801750": ("计算机", "Computers"),
    "801760": ("传媒", "Media"),
    "801770": ("通信", "Telecoms"),
    "801780": ("银行", "Banks"),
    "801790": ("非银金融", "Non-bank Financials"),
    "801880": ("汽车", "Automobiles"),
    "801890": ("机械设备", "Machinery"),
    "801950": ("煤炭", "Coal"),
    "801960": ("石油石化", "Oil & Petrochem"),
    "801970": ("环保", "Environmental"),
    "801980": ("美容护理", "Beauty & Care"),
}

# index_hist_sw column (Chinese) -> stored column
_HIST_COLS = {
    "收盘": "close", "开盘": "open", "最高": "high",
    "最低": "low", "成交量": "volume", "成交额": "amount",
}


class ChinaSectorsAdapter(Adapter):
    name = "china_sectors"
    group = "china_sectors"
    stale_after_days = 6   # daily index; allow a long weekend / holiday

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import akshare as ak  # lazy: heavy import, only needed at collect time

        out: dict[str, pd.DataFrame] = {}
        for code, (cn, en) in SW_L1.items():
            try:
                raw = ak.index_hist_sw(symbol=code, period="day")
            except Exception as e:  # noqa: BLE001 — per-code isolation
                log.warning("china_sectors %s (%s) history failed: %s", code, en, e)
                continue
            if raw is None or raw.empty or "日期" not in raw.columns:
                log.warning("china_sectors %s (%s): empty/unexpected payload", code, en)
                continue
            df = pd.DataFrame(index=pd.to_datetime(raw["日期"]))
            for src, dst in _HIST_COLS.items():
                if src in raw.columns:
                    df[dst] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
            df = df.dropna(subset=["close"])
            if not df.empty:
                out[code] = df.sort_index()

        if not out:
            raise RuntimeError("china_sectors: no Shenwan industry returned data")

        # -- valuation snapshot (append one row/day -> accruing own-history) ---------
        try:
            info = ak.sw_index_first_info()
            row: dict[str, float] = {}
            for _, r in info.iterrows():
                code = str(r.get("行业代码", "")).split(".")[0]
                if code not in SW_L1:
                    continue
                row[f"{code}_pe_ttm"] = pd.to_numeric(r.get("TTM(滚动)市盈率"), errors="coerce")
                row[f"{code}_pb"] = pd.to_numeric(r.get("市净率"), errors="coerce")
                row[f"{code}_div"] = pd.to_numeric(r.get("静态股息率"), errors="coerce")
            if row:
                asof = pd.Timestamp.now().normalize()
                out["valuation"] = pd.DataFrame([row], index=pd.DatetimeIndex([asof]))
        except Exception as e:  # noqa: BLE001 — valuation is additive context
            log.warning("china_sectors valuation snapshot failed: %s", e)

        return out
