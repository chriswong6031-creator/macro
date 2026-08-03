"""Multi-market sector treemap heatmap — pure compute layer (China / HK / Canada).

The international sibling of ``engine/sp500_heatmap.py``. The US map is a
three-level treemap (Sector → Sub-industry → stock) because we carry a curated
Finviz sub-industry map for the 503 names. The CN / HK / CA universes only carry
a **sector** classification, so these maps are a *flat* two-level treemap
(Sector → stock) — exactly how TradingView's HSI / TSX / SZSE heatmaps group.
The shared front-end (``site/heatmap.js``) renders this with ``map_type:"stocks"``.

Design notes
------------
* **Pure** — takes already-loaded pandas objects / dicts, returns a
  JSON-serialisable dict. All disk I/O lives in
  ``scripts/build_market_heatmap.py`` so the maths stays unit-testable and
  offline-safe.
* Returns reuse ``engine.sp500_heatmap.daily_returns`` (1D/1W/MTD/1M/3M/6M/YTD/1Y
  from the daily close matrix). No live/intraday feed is wired for these markets
  yet, so the intraday / after-hours toggles stay greyed (same contract as US).
* Box size = real market cap when supplied (China: ``mktcap_yi``; Canada/HK:
  fundamentals ``marketCap``); else the index ``weight`` as a proxy; else equal.
  Missing/zero sizes are floored so every constituent still draws.
* Each market carries its own ``currency`` (CNY / HKD / CAD), the per-stock
  hover-card directory (``stockdata_dir``) and the analyzer click-through
  (``stock_url``) so the one shared renderer routes to the right surface.
"""
from __future__ import annotations

import re
from typing import Mapping

import pandas as pd

from engine import sp500_heatmap as us  # reuse daily_returns + the timeframe contract

_DMA_WINDOW = 200        # the "vs 200d" tag's window
_MIN_DMA_OBS = 200       # never print a 200-day average from fewer than 200 prints

# ---------------------------------------------------------------------------
# Per-market Sector → Chinese label maps. Keys must match the ``sector`` strings
# in each market's members/constituents table. English label = the key itself.
# ---------------------------------------------------------------------------
SECTOR_ZH_CN: dict[str, str] = {
    "Technology": "信息技术",
    "Industrials": "工业",
    "Basic Materials": "材料",
    "Healthcare": "医疗保健",
    "Consumer Cyclical": "非必需消费",
    "Financial Services": "金融",
    "Consumer Defensive": "必需消费",
    "Utilities": "公用事业",
    "Communication Services": "通信服务",
    "Energy": "能源",
    "Real Estate": "房地产",
    "A-share": "其他",
}

SECTOR_ZH_HK: dict[str, str] = {
    "Internet & Tech": "互联网与科技",
    "Consumer": "消费",
    "Property": "地产",
    "Financials & Banks": "金融与银行",
    "Healthcare & Pharma": "医药健康",
    "Energy": "能源",
    "Telecom & Utilities": "电信与公用事业",
    "Materials": "材料",
    "Auto & EV": "汽车与新能源车",
    "Industrials & Transport": "工业与运输",
    "Insurance": "保险",
    "Exchange & Diversified": "交易所与综合",
    "Gaming & Leisure": "博彩与休闲",
}

SECTOR_ZH_CA: dict[str, str] = {
    "Financials": "金融",
    "Materials": "材料",
    "Energy": "能源",
    "Industrials": "工业",
    "Information Technology": "信息技术",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
    "Consumer Staples": "必需消费",
    "Consumer Discretionary": "非必需消费",
    "Communication": "通信",
    "Health Care": "医疗保健",
    # defensive aliases — the canada_search table uses the GICS spellings above,
    # but yfinance fundamentals occasionally return these variants; keep both so a
    # spelling drift upstream still resolves to a Chinese label.
    "Communication Services": "通信服务",
    "Healthcare": "医疗保健",
}

# HK ticker -> Chinese short name. HK carries no Chinese-name feed (the breadth
# constituents table is symbol / English name / sector only), so this curated map
# is the source for the heatmap's tile labels. Clean short names (no HKEX -W/-SW
# suffixes) to match the CN convention. Names absent here fall back to the English
# name in the renderer (name_zh -> name -> ticker), so a new constituent degrades
# gracefully; add it here to give it a Chinese label.
HK_NAME_ZH: dict[str, str] = {
    "0700.HK": "腾讯控股", "0981.HK": "中芯国际", "9988.HK": "阿里巴巴",
    "1347.HK": "华虹半导体", "0992.HK": "联想集团", "1810.HK": "小米集团",
    "3690.HK": "美团", "1299.HK": "友邦保险", "0883.HK": "中国海油",
    "1211.HK": "比亚迪股份", "0939.HK": "建设银行", "0005.HK": "汇丰控股",
    "2318.HK": "中国平安", "1024.HK": "快手", "2899.HK": "紫金矿业",
    "0388.HK": "香港交易所", "2382.HK": "舜宇光学", "0941.HK": "中国移动",
    "9999.HK": "网易", "9926.HK": "康方生物", "9888.HK": "百度集团",
    "1378.HK": "中国宏桥", "2628.HK": "中国人寿", "3988.HK": "中国银行",
    "9618.HK": "京东集团", "1398.HK": "工商银行", "0857.HK": "中国石油",
    "9868.HK": "小鹏汽车", "1801.HK": "信达生物", "2015.HK": "理想汽车",
    "1109.HK": "华润置地", "2269.HK": "药明生物", "0175.HK": "吉利汽车",
    "9961.HK": "携程集团", "3993.HK": "洛阳钼业", "6160.HK": "百济神州",
    "0016.HK": "新鸿基地产", "2359.HK": "药明康德", "2338.HK": "潍柴动力",
    "9626.HK": "哔哩哔哩", "3968.HK": "招商银行", "1093.HK": "石药集团",
    "0763.HK": "中兴通讯", "2600.HK": "中国铝业", "2388.HK": "中银香港",
    "0669.HK": "创科实业", "1088.HK": "中国神华", "0358.HK": "江西铜业",
    "2020.HK": "安踏体育", "0001.HK": "长和", "1288.HK": "农业银行",
    "0688.HK": "中国海外发展", "3888.HK": "金山软件", "0386.HK": "中国石化",
    "1336.HK": "新华保险", "0823.HK": "领展房产基金", "0268.HK": "金蝶国际",
    "1208.HK": "五矿资源", "6618.HK": "京东健康", "0836.HK": "华润电力",
    "0728.HK": "中国电信", "2601.HK": "中国太保", "0241.HK": "阿里健康",
    "1177.HK": "中国生物制药", "0027.HK": "银河娱乐", "9863.HK": "零跑汽车",
    "2319.HK": "蒙牛乳业", "0288.HK": "万洲国际", "0285.HK": "比亚迪电子",
    "2331.HK": "李宁", "3692.HK": "翰森制药", "1072.HK": "东方电气",
    "2057.HK": "中通快递", "0902.HK": "华能国际电力", "9633.HK": "农夫山泉",
    "2313.HK": "申洲国际", "0012.HK": "恒基地产", "2688.HK": "新奥能源",
    "0006.HK": "电能实业", "9698.HK": "万国数据", "1113.HK": "长实集团",
    "0998.HK": "中信银行", "1929.HK": "周大福", "1898.HK": "中煤能源",
    "0002.HK": "中电控股", "0762.HK": "中国联通", "0291.HK": "华润啤酒",
    "2888.HK": "渣打集团", "6862.HK": "海底捞", "0322.HK": "康师傅控股",
    "3328.HK": "交通银行", "3800.HK": "协鑫科技", "1928.HK": "金沙中国",
    "1209.HK": "华润万象生活", "0966.HK": "中国太平", "0003.HK": "中华煤气",
    "1658.HK": "邮储银行", "0066.HK": "港铁公司", "0780.HK": "同程旅行",
    "0316.HK": "东方海外国际", "1038.HK": "长江基建", "2333.HK": "长城汽车",
    "0960.HK": "龙湖集团", "0772.HK": "阅文集团", "1816.HK": "中广核电力",
    "0083.HK": "信和置业", "1766.HK": "中国中车", "1099.HK": "国药控股",
    "6060.HK": "众安在线", "0390.HK": "中国中铁", "1997.HK": "九龙仓置业",
    "2007.HK": "碧桂园", "1044.HK": "恒安国际", "1066.HK": "威高股份",
    "1833.HK": "平安好医生", "6969.HK": "思摩尔国际", "0019.HK": "太古股份公司",
    "0135.HK": "昆仑能源", "2282.HK": "美高梅中国", "0257.HK": "光大环境",
    "0101.HK": "恒隆地产", "1359.HK": "中国信达", "3618.HK": "重庆农商行",
    "2883.HK": "中海油田服务", "6818.HK": "光大银行", "0867.HK": "康哲药业",
    "0014.HK": "希慎兴业", "1057.HK": "浙江世宝", "0392.HK": "北京控股",
    "0371.HK": "北控水务", "0144.HK": "招商局港口", "0017.HK": "新世界发展",
    "2196.HK": "上海医药", "0683.HK": "嘉里建设", "0639.HK": "首钢资源",
    "6098.HK": "碧桂园服务", "0151.HK": "中国旺旺", "0656.HK": "复星国际",
    "2607.HK": "复宏汉霖", "1186.HK": "中国铁建", "2238.HK": "广汽集团",
    "6808.HK": "高鑫零售", "1112.HK": "健合集团", "0323.HK": "马鞍山钢铁",
    "0880.HK": "澳博控股", "2378.HK": "保诚", "0345.HK": "维他奶国际",
    "0200.HK": "新濠国际发展", "0778.HK": "置富产业信托", "0934.HK": "中石化冠德",
    "1958.HK": "北京汽车", "1799.HK": "新特能源", "0884.HK": "旭辉控股集团",
    "2150.HK": "奈雪的茶", "0486.HK": "俄铝", "2392.HK": "康龙化成",
    "3333.HK": "中国恒大",
}


# Per-market presentation contract consumed by the front-end. ``currency`` drives
# the hover-card market-cap formatting (亿/万亿 for CNY, B/T otherwise);
# ``stockdata_dir`` is the per-stock conviction-read directory; ``stock_url`` is
# the analyzer the tile / mobile row links to (``<url><ticker>``).
MARKETS: dict[str, dict] = {
    "china": {
        "currency": "CNY",
        "stockdata_dir": "chinastockdata",
        "stock_url": "https://app.mastermind-x.com/terminal?symbol=",
        "sector_zh": SECTOR_ZH_CN,
        "label_en": "China A-shares",
        "label_zh": "A股",
        "size_label_en": "Mkt cap",
        "size_label_zh": "市值",
        # Label tiles by company name, not the opaque 6-digit A-share code. The
        # renderer prefers name_zh (always present for CN), else the English name,
        # else the ticker.
        "tile_label": "name",
    },
    "hk": {
        # HK carries no shares-outstanding feed, so tiles are sized by average
        # dollar turnover (a liquidity proxy that tracks size/importance) —
        # labelled as turnover, never mislabelled as market cap.
        "currency": "HKD",
        "stockdata_dir": "hkstockdata",
        "stock_url": "https://app.mastermind-x.com/terminal?symbol=",
        "sector_zh": SECTOR_ZH_HK,
        "label_en": "Hong Kong",
        "label_zh": "港股",
        "size_label_en": "Avg turnover",
        "size_label_zh": "日均成交额",
        # Label tiles by company name, not the 4-digit HK code. HK carries no
        # Chinese-name feed yet, so the renderer falls back to the English name
        # (Tencent, Alibaba…) — still far more legible than "0700".
        "tile_label": "name",
    },
    "canada": {
        "currency": "CAD",
        "stockdata_dir": "canadastockdata",
        "stock_url": "https://app.mastermind-x.com/terminal?symbol=",
        "sector_zh": SECTOR_ZH_CA,
        "label_en": "Canada · TSX",
        "label_zh": "加拿大 · TSX",
        "size_label_en": "Mkt cap",
        "size_label_zh": "市值",
    },
}


# Per-market standalone-page copy (consumed by scripts/build_site.py rendering
# templates/market_heatmap.html.j2). Kept here so the engine is the single source
# of truth for everything market-specific.
#
# `seo_title` / `seo_desc` are the ONE title each page carries — <title>, og:,
# twitter: and the SERP line all read them (SEO_SUPERCHARGE W2 spec §A8). The page
# used to carry three different strings; a searcher types entity nouns ("A-share",
# "TSX", "heatmap", "sector"), not product vocabulary, so each leads with those and
# ends with the brand. Titles stay ≤ 70 chars and descriptions inside 50–170 —
# pinned by tests/test_china_heatmap_gate.py.
PAGE_META: dict[str, dict] = {
    "china": {
        "icon": "🔥", "key": "china", "json": "marketdata/china_heatmap.json",
        "title": "China A-share Heatmap",
        "seo_title": "China A-Share Heatmap — Live Sector Map — MastermindX",
        "seo_desc": ("Every liquid Shanghai and Shenzhen A-share as one sector treemap — "
                     "today's winners, losers and sector breadth, sized by market cap, "
                     "after each close."),
        "label_en": "China A-shares", "label_zh": "A股",
        "h1_en": "China A-share Heatmap", "h1_zh": "A股市场热力图",
        "sub_en": "Every liquid A-share as a tile, grouped <b>Sector → stock</b> and sized by <b>market cap</b> — the institutional treemap in our theme. Tiles shade by the move over the timeframe you pick; hover a tile for our conviction read, or a sector header for its members, and click through to the analyzer.",
        "sub_zh": "每只活跃 A 股一个方块，按「<b>板块 → 个股</b>」分组、按<b>市值</b>定大小 —— 采用我们主题配色的机构级树图。方块按所选周期的涨跌幅着色；悬停方块查看我们的研判，悬停板块标题查看其成员，点击进入分析器。",
        "foot_en": "Green = up, red = down (inverted in 中文 to the Asian convention); the 1D view bins at ±1/2/3%, longer windows widen the bins so the map stays legible. Tiles are sized by market cap and computed from adjusted closes; the hover card is our own conviction read (verdict, 0–100 score, drivers and cautions) — research context, never a buy signal.",
        "foot_zh": "绿涨红跌（中文模式按亚洲习惯反转）；1天视图采用 ±1/2/3% 分档，更长周期会拓宽分档以保持可读性。方块按市值定大小、由复权收盘价计算；悬停卡片为我们自有的研判（结论、0–100 评分、驱动与风险）—— 仅作研究参考，绝非买入信号。",
    },
    "hk": {
        "icon": "🔥", "key": "hk", "json": "marketdata/hk_heatmap.json",
        "title": "Hong Kong Stock Heatmap",
        "seo_title": "Hong Kong Stock Heatmap — Sector Map — MastermindX",
        "seo_desc": ("Every liquid Hong Kong listing as one sector treemap — today's "
                     "winners, losers and sector breadth, sized by average turnover, "
                     "after each close."),
        "label_en": "Hong Kong", "label_zh": "港股",
        "h1_en": "Hong Kong Stock Heatmap", "h1_zh": "港股市场热力图",
        "sub_en": "The Hong Kong universe as a tile each, grouped <b>Sector → stock</b> and sized by <b>average dollar turnover</b> (a liquidity proxy — HK carries no shares-outstanding feed). Tiles shade by the move over the timeframe you pick; hover a tile for our conviction read, or a sector header for its members, and click through to the analyzer.",
        "sub_zh": "港股标的逐一成块，按「<b>板块 → 个股</b>」分组、按<b>日均成交额</b>定大小（流动性代理 —— 港股无流通股本数据源）。方块按所选周期的涨跌幅着色；悬停方块查看我们的研判，悬停板块标题查看其成员，点击进入分析器。",
        "foot_en": "Green = up, red = down (inverted in 中文 to the Asian convention); the 1D view bins at ±1/2/3%, longer windows widen the bins. Tiles are sized by average dollar turnover (a size/importance proxy where no shares feed exists) and coloured from adjusted closes; the hover card is our own conviction read — research context, never a buy signal.",
        "foot_zh": "绿涨红跌（中文模式按亚洲习惯反转）；1天视图采用 ±1/2/3% 分档，更长周期会拓宽分档。方块按日均成交额定大小（在无流通股本数据时作为规模/重要性的代理），由复权收盘价着色；悬停卡片为我们自有的研判 —— 仅作研究参考，绝非买入信号。",
    },
    "canada": {
        "icon": "🔥", "key": "canada", "json": "marketdata/canada_heatmap.json",
        "title": "Canada · TSX Heatmap",
        "seo_title": "Canada TSX Heatmap — Sector Map — MastermindX",
        "seo_desc": ("Every liquid TSX listing as one sector treemap — today's winners, "
                     "losers and sector breadth, sized by market cap, updated nightly."),
        "label_en": "Canada · TSX", "label_zh": "加拿大 · TSX",
        "h1_en": "Canada · TSX Heatmap", "h1_zh": "加拿大 · TSX 热力图",
        "sub_en": "The TSX universe as a tile each, grouped <b>Sector → stock</b> and sized by <b>market cap</b> — the institutional treemap in our theme. Tiles shade by the move over the timeframe you pick; hover a tile for our conviction read, or a sector header for its members, and click through to the analyzer.",
        "sub_zh": "多伦多交易所标的逐一成块，按「<b>板块 → 个股</b>」分组、按<b>市值</b>定大小 —— 采用我们主题配色的机构级树图。方块按所选周期的涨跌幅着色；悬停方块查看我们的研判，悬停板块标题查看其成员，点击进入分析器。",
        "foot_en": "Green = up, red = down (inverted in 中文 to the Asian convention); the 1D view bins at ±1/2/3%, longer windows widen the bins so the map stays legible. Tiles are sized by market cap and computed from adjusted closes; the hover card is our own conviction read (verdict, 0–100 score, drivers and cautions) — research context, never a buy signal.",
        "foot_zh": "绿涨红跌（中文模式按亚洲习惯反转）；1天视图采用 ±1/2/3% 分档，更长周期会拓宽分档以保持可读性。方块按市值定大小、由复权收盘价计算；悬停卡片为我们自有的研判（结论、0–100 评分、驱动与风险）—— 仅作研究参考，绝非买入信号。",
    },
}


def _float_sizes(
    rows: list[dict],
    caps: Mapping[str, float] | None,
    weights: Mapping[str, float] | None,
) -> tuple[dict[str, float], str]:
    """Box sizes + the basis label. Real caps win; else index weight; else equal.

    Whichever basis we land on, any missing/zero value is floored at half the
    smallest positive size so every constituent still draws a (small) tile —
    mirroring the US builder's behaviour.
    """
    syms = [r["t"] for r in rows]

    def _floored(src: Mapping[str, float]) -> dict[str, float]:
        vals = {t: float(src.get(t, 0.0) or 0.0) for t in syms}
        pos = [v for v in vals.values() if v > 0]
        floor = (min(pos) * 0.5) if pos else 1.0
        return {t: (v if v > 0 else floor) for t, v in vals.items()}

    if caps and any((caps.get(t) or 0) > 0 for t in syms):
        return _floored(caps), "marketcap"
    if weights and any((weights.get(t) or 0) > 0 for t in syms):
        return _floored(weights), "weight_proxy"
    return {t: 1.0 for t in syms}, "equal"


# Scope copy for the whole-board breadth block. Named per market so the card can say
# WHAT the count is out of — a 涨跌家数 with an unstated denominator is the exact defect
# this block exists to fix (the tile-derived count read as a whole-board print).
_BOARD_SCOPE: dict[str, dict[str, str]] = {
    "china": {"en": "Shanghai + Shenzhen A-shares", "zh": "沪深全市场"},
}


def _board_breadth_block(market: str, row: Mapping | None, asof_date: str) -> dict | None:
    """Validate + shape one whole-board adv/dec row for the payload, or None.

    Returned ONLY when the row describes the SAME session the tiles do. A board count
    from a different session sitting beside a fresh tile map is worse than no board
    count at all — the card would silently mix two days, and the fallback (counting
    tiles) is at least internally consistent. Anything missing, malformed, or
    stale-dated falls through to that fallback.
    """
    scope = _BOARD_SCOPE.get(market)
    if not row or not scope or not asof_date:
        return None
    if str(row.get("date") or "") != asof_date:
        return None
    try:
        n, adv, dec = int(row["n"]), int(row["adv"]), int(row["dec"])
    except (KeyError, TypeError, ValueError):
        return None
    if n <= 0 or adv < 0 or dec < 0 or adv + dec > n:
        return None
    flat = n - adv - dec
    med = row.get("med_pct")
    return {
        "n": n, "adv": adv, "dec": dec, "flat": flat,
        "pct_up": round(100.0 * adv / n, 2),
        "med_pct": None if med is None else round(float(med), 2),
        "scope_en": scope["en"], "scope_zh": scope["zh"],
        "source": str(row.get("source") or ""),
    }


def _market_facts(closes: pd.DataFrame, asof: pd.Timestamp | None) -> dict[str, dict[str, float]]:
    """ticker -> {'px': last close, 'p200': % vs its 200-day average}.

    Both are MARKET FACTS, not grades. They used to reach the hover card only
    inside ``<market>stockdata/<T>.json`` — the file that also carries our graded
    conviction block — so an anonymous card lost two honest numbers to protect a
    third thing entirely (W2 spec T-A2, MITIGATE ruling). Carrying them on the
    tile keeps the free card useful and leaves the graded block as the only thing
    the wall is actually about.

    ``p200`` is omitted (not zeroed, not extrapolated) below 200 observations: a
    "200-day average" printed off 40 prints is a different statistic wearing the
    same label.
    """
    out: dict[str, dict[str, float]] = {}
    if closes is None or closes.empty:
        return out
    frame = closes.sort_index()
    if asof is not None:
        frame = frame.loc[:pd.Timestamp(asof)]
    if frame.empty:
        return out
    for col in frame.columns:
        s = frame[col].dropna()
        if s.empty:
            continue
        last = float(s.iloc[-1])
        if not (last > 0):
            continue
        fact: dict[str, float] = {"px": round(last, 4)}
        if len(s) >= _MIN_DMA_OBS:
            dma = float(s.iloc[-_DMA_WINDOW:].mean())
            if dma > 0:
                fact["p200"] = round((last / dma - 1.0) * 100.0, 2)
        out[str(col)] = fact
    return out


def build_market_heatmap(
    market: str,
    constituents: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    caps: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
    names_zh: Mapping[str, str] | None = None,
    generated_utc: str | None = None,
    asof: pd.Timestamp | None = None,
    board_breadth: Mapping | None = None,
) -> dict:
    """Assemble a flat (Sector → stock) heatmap payload for one market.

    Parameters
    ----------
    market       : 'china' | 'hk' | 'canada' (selects the presentation contract).
    constituents : index = ticker, columns include ['name', 'sector'].
    closes       : daily close matrix (Date index, ticker columns).
    caps         : ticker -> market cap (market currency, absolute). Sizes tiles.
    weights      : ticker -> index weight_pct — proxy size when no caps.
    names_zh     : ticker -> Chinese display name (China only; optional).
    board_breadth: one whole-board adv/dec row (see _board_breadth_block).
    """
    cfg = MARKETS[market]
    if constituents is None or constituents.empty:
        return _empty_payload(market, cfg, generated_utc)

    perf = us.daily_returns(closes, asof=asof)

    closes_sorted = closes.sort_index() if closes is not None and not closes.empty else closes
    asof_date = ""
    if closes_sorted is not None and not closes_sorted.empty:
        asof_date = pd.Timestamp(asof or closes_sorted.index[-1]).strftime("%Y-%m-%d")

    rows: list[dict] = []
    for sym, row in constituents.iterrows():
        sector = str(row.get("sector") or "").strip()
        if not sector:
            continue
        rows.append({
            "t": sym,
            "name": str(row.get("name") or sym),
            "name_zh": str((names_zh or {}).get(sym) or "").strip(),
            "sector": sector,
        })

    sizes, size_basis = _float_sizes(rows, caps, weights)
    facts = _market_facts(closes_sorted, asof)

    tiles: list[dict] = []
    for r in rows:
        sym = r["t"]
        p = dict(perf.get(sym, {}))
        # Drop names with no return data at all — an uncolorable tile is a dead
        # grey square (e.g. an index constituent whose price series is absent);
        # omit it rather than render a meaningless blank.
        if not p:
            continue
        tile = {
            "t": sym,
            "name": r["name"],
            "sector": r["sector"],
            "size": round(float(sizes.get(sym, 0.0)), 6),
            "perf": p,
        }
        if r["name_zh"] and r["name_zh"] != r["name"]:
            tile["name_zh"] = r["name_zh"]
        tile.update(facts.get(str(sym), {}))
        tiles.append(tile)

    # A timeframe lights up only once enough constituents carry it (keeps a
    # thinly-covered window greyed instead of rendering a mostly-grey map).
    n = len(tiles) or 1
    counts: dict[str, int] = {}
    for tile in tiles:
        for k in tile["perf"]:
            counts[k] = counts.get(k, 0) + 1
    timeframes = [
        {**tf, "available": (counts.get(tf["key"], 0) / n) >= us.MIN_COVERAGE}
        for tf in us.TIMEFRAMES
    ]

    sector_zh = cfg["sector_zh"]
    sectors_present = []
    seen = set()
    for r in rows:
        if r["sector"] not in seen:
            seen.add(r["sector"])
            sectors_present.append({
                "key": r["sector"],
                "en": r["sector"],
                "zh": sector_zh.get(r["sector"], r["sector"]),
            })

    board = _board_breadth_block(market, board_breadth, asof_date)

    return {
        "market": market,
        "map_type": "stocks",
        "asof": asof_date,
        "generated_utc": generated_utc or "",
        "source": "daily-close",
        "delay_min": 0,
        "currency": cfg["currency"],
        "stockdata_dir": cfg["stockdata_dir"],
        "stock_url": cfg["stock_url"],
        "label_en": cfg.get("label_en", ""),
        "label_zh": cfg.get("label_zh", ""),
        "size_label_en": cfg["size_label_en"],
        "size_label_zh": cfg["size_label_zh"],
        "tile_label": cfg.get("tile_label", "ticker"),
        "default_tf": us.DEFAULT_TIMEFRAME,
        "timeframes": timeframes,
        "sectors": sectors_present,
        "tiles": tiles,
        "n_tiles": len(tiles),
        "size_basis": size_basis,
        # Whole-board 涨跌家数 for the SAME session as the tiles, when we have it.
        # Absent (or stale) → the front-end counts tiles, as it always did.
        **({"board_breadth": board} if board else {}),
    }


def _empty_payload(market: str, cfg: dict, generated_utc: str | None) -> dict:
    return {
        "market": market,
        "map_type": "stocks",
        "asof": "",
        "generated_utc": generated_utc or "",
        "source": "daily-close",
        "delay_min": 0,
        "currency": cfg["currency"],
        "stockdata_dir": cfg["stockdata_dir"],
        "stock_url": cfg["stock_url"],
        "label_en": cfg.get("label_en", ""),
        "label_zh": cfg.get("label_zh", ""),
        "size_label_en": cfg["size_label_en"],
        "size_label_zh": cfg["size_label_zh"],
        "tile_label": cfg.get("tile_label", "ticker"),
        "default_tf": us.DEFAULT_TIMEFRAME,
        "timeframes": [{**tf, "available": False} for tf in us.TIMEFRAMES],
        "sectors": [],
        "tiles": [],
        "n_tiles": 0,
        "size_basis": "equal",
    }


# ---------------------------------------------------------------------------
#  SERVER-RENDERED PAGE SUMMARY (SEO Supercharge W2, spec §A2.3)
# ---------------------------------------------------------------------------
#  `templates/market_heatmap.html.j2` used to ship a 76-line shell: a header, an
#  empty <div id="heatmap-full">, a footer. Every number on the page was built at
#  runtime by heatmap.js from the tile JSON, so a crawler — and anyone with JS
#  off — got one sentence: "Could not load heatmap data." Opening that page to
#  anonymous visitors would have handed Google a thin-content 200 in place of a
#  302: a worse failure, because Google KEEPS it and rates it thin.
#
#  So the conversion is a CONTENT build. These functions compute, in Python and
#  from the same payload the map draws, exactly what heatmap.js's renderPulse /
#  renderStats / renderBoards compute client-side: the market pulse, the four
#  breadth stat cards, the sector ladder and the two mover boards. The template
#  renders them as static HTML; heatmap.js REPLACES them the moment live data
#  draws, so the SSR copy is the crawlable floor and the JS copy stays the live
#  truth. The arithmetic below is a deliberate mirror — pinned against the JS
#  source in tests/test_china_heatmap_gate.py.
#
#  Nothing here is graded. Breadth, medians, sector aggregates and biggest movers
#  are arithmetic over public closes; the one graded surface on this page (our
#  per-name conviction read) lives in a separate fetched file and never enters
#  this summary.

_ADV_BAND = 0.05          # ±% dead-band for advancing/declining (mirrors heatmap.js)
_MOVERS = 5               # rows per mover board


def _fmt_pc(v: float | None) -> str:
    """heatmap.js fmtPc, character for character (U+2212 MINUS, not a hyphen)."""
    if v is None:
        return "—"
    a = abs(float(v))
    d = 0 if a >= 100 else (1 if a >= 10 else 2)
    sign = "+" if v > 0 else ("−" if v < 0 else "")
    return f"{sign}{a:.{d}f}%"


def _fmt_int(v: float | None) -> str:
    return "—" if v is None else f"{round(float(v)):,}"


def _disp_t(t: str) -> str:
    """Tile display ticker — strip the exchange suffix (heatmap.js dispT)."""
    return re.sub(r"\.(SS|SZ|SH|HK|TO|V|TSX|NE|CN)$", "", str(t), flags=re.I)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def _sector_agg(size_basis: str, tiles: list[dict], tf: str) -> float | None:
    """Cap-weighted where sizes are real caps, median otherwise (heatmap.js sectorAgg)."""
    vals = [(t, t["perf"][tf]) for t in tiles if t.get("perf", {}).get(tf) is not None]
    if not vals:
        return None
    if size_basis == "marketcap":
        num = sum(float(t.get("size") or 0.0) * v for t, v in vals)
        den = sum(float(t.get("size") or 0.0) for t, _ in vals)
        return (num / den) if den > 0 else None
    return _median([v for _, v in vals])


def _median_word(v: float | None) -> dict[str, str] | None:
    if v is None:
        return None
    if abs(v) < 0.25:
        return {"en": "Flat — no drift", "zh": "基本走平"}
    return ({"en": "Tilted higher", "zh": "偏强"} if v > 0
            else {"en": "Tilted lower", "zh": "偏弱"})


def _stance(pct_up: float, med: float, secs: list[dict]) -> dict[str, str]:
    """Deterministic plain-word read of the tape (heatmap.js stanceOf).

    Breadth + leadership arithmetic only — no model, no LLM, no graded input.
    This is the page's Law-1 stance for an anonymous reader (spec §A6).
    """
    top = secs[0] if secs else None
    led = bool(top and top["agg"] > 1.2)
    if pct_up >= 60 and med > 0.2:
        return {"tone": "up", "en": "Broad advance", "zh": "普涨"}
    if pct_up <= 40 and med < -0.2:
        return {"tone": "down", "en": "Broad decline", "zh": "普跌"}
    if led and pct_up < 52:
        return {"tone": "flat", "en": f"Narrow · led by {top['en']}", "zh": "结构性行情"}
    if pct_up >= 54:
        return {"tone": "up", "en": "Firmer tape", "zh": "偏强"}
    if pct_up <= 46:
        return {"tone": "down", "en": "Softer tape", "zh": "偏弱"}
    return {"tone": "flat", "en": "Split tape", "zh": "涨跌分化"}


def page_summary(payload: Mapping | None) -> dict | None:
    """The crawlable summary layer for one market's standalone heatmap page.

    Returns None when the payload carries nothing renderable, so the template can
    fall back to the shell it has always shipped rather than print empty blocks.
    """
    if not payload:
        return None
    tiles = list(payload.get("tiles") or [])
    if not tiles:
        return None

    tf = str(payload.get("default_tf") or "1D")
    frames = list(payload.get("timeframes") or [])
    if not any(f.get("key") == tf and f.get("available") for f in frames):
        avail = [f["key"] for f in frames if f.get("available")]
        if not avail:
            return None
        tf = avail[0]

    ts = [t for t in tiles if t.get("perf", {}).get(tf) is not None]
    if not ts:
        return None

    adv = sum(1 for t in ts if t["perf"][tf] > _ADV_BAND)
    dec = sum(1 for t in ts if t["perf"][tf] < -_ADV_BAND)
    flat = len(ts) - adv - dec
    n = len(ts)
    pct_up = (adv / n * 100.0) if n else 0.0
    med = _median([t["perf"][tf] for t in ts])

    size_basis = str(payload.get("size_basis") or "")
    labels = {s["key"]: s for s in (payload.get("sectors") or [])}
    by_sector: dict[str, list[dict]] = {}
    for t in ts:
        by_sector.setdefault(t["sector"], []).append(t)
    secs: list[dict] = []
    for key, group in by_sector.items():
        agg = _sector_agg(size_basis, group, tf)
        if agg is None:
            continue
        lab = labels.get(key, {})
        secs.append({"key": key, "en": lab.get("en", key), "zh": lab.get("zh", key),
                     "agg": agg, "n": len(group)})
    secs.sort(key=lambda s: s["agg"], reverse=True)

    ranked = sorted(ts, key=lambda t: t["perf"][tf], reverse=True)
    gainers, losers = ranked[:_MOVERS], list(reversed(ranked[-_MOVERS:]))

    # Whole-board 涨跌家数 overlay: the tiles are a SAMPLE of a bigger board (China
    # ~1.5k of ~5.2k names), so where a same-session whole-board row exists we quote
    # THAT for the counts, the % up and the median — one sentence, one universe.
    # Per-name detail (movers, sector strength) stays tile-derived: the board feed
    # carries no names. Mirrors heatmap.js applyBoard, including its 1D-only gate.
    scope = None
    board = payload.get("board_breadth") or None
    if board and tf == str(payload.get("default_tf") or "1D") and (board.get("n") or 0) > 0:
        adv, dec, flat = board["adv"], board["dec"], board["flat"]
        n, pct_up = board["n"], board["pct_up"]
        if board.get("med_pct") is not None:
            med = board["med_pct"]
        scope = {
            "en": f"{board['scope_en']} · {_fmt_int(board['n'])} traded",
            "zh": f"{board['scope_zh']} · {_fmt_int(board['n'])} 只交易",
        }
    elif str(payload.get("market") or "") == "china":
        # China is the one market whose coverage gap is MEASURED, so it is the one
        # market that may name its denominator. Never assert a coverage claim for a
        # market where we have not measured one.
        scope = {"en": f"Map sample · {_fmt_int(n)} names",
                 "zh": f"本图样本 · {_fmt_int(n)} 只"}

    tot = max(1, adv + dec + flat)
    top, bot = (secs[0] if secs else None), (secs[-1] if secs else None)

    def _mover(t: dict, max_abs: float) -> dict:
        v = t["perf"][tf]
        w = max(6.0, min(100.0, abs(v) / max_abs * 100.0)) if max_abs > 0 else 0.0
        return {
            "code": _disp_t(t["t"]),
            "name_en": t.get("name") or _disp_t(t["t"]),
            "name_zh": t.get("name_zh") or t.get("name") or _disp_t(t["t"]),
            "pc": _fmt_pc(v), "up": v >= 0, "w": round(w),
        }

    g_max = max((abs(t["perf"][tf]) for t in gainers), default=0.0)
    l_max = max((abs(t["perf"][tf]) for t in losers), default=0.0)
    s_max = max((abs(s["agg"]) for s in secs), default=0.0)

    return {
        "tf": tf,
        "asof": str(payload.get("asof") or ""),
        "n_tiles": int(payload.get("n_tiles") or len(tiles)),
        "stance": _stance(pct_up, med or 0.0, secs),
        "pct_up": round(pct_up),
        "median": _fmt_pc(med),
        "median_word": _median_word(med),
        "median_tone": "up" if (med or 0) > 0 else ("down" if (med or 0) < 0 else ""),
        "breadth": {
            "adv": _fmt_int(adv), "dec": _fmt_int(dec),
            "adv_w": round(100.0 * adv / tot, 2),
            "flat_w": round(100.0 * flat / tot, 2),
            "dec_w": round(100.0 * dec / tot, 2),
            "scope": scope,
        },
        # Where the tape is strong / weak, in plain words. Two each side, and only
        # sectors that actually moved (±0.05%) — mirrors heatmap.js _leadPhrase.
        "up_sectors": [{"en": s["en"], "zh": s["zh"]} for s in secs if s["agg"] > 0.05][:2],
        "down_sectors": [{"en": s["en"], "zh": s["zh"]}
                         for s in secs if s["agg"] < -0.05][-2:][::-1],
        "top": (None if not top else
                {"en": top["en"], "zh": top["zh"], "pc": _fmt_pc(top["agg"]),
                 "tone": "up" if top["agg"] >= 0 else "down"}),
        "bot": (None if (not bot or bot is top) else
                {"en": bot["en"], "zh": bot["zh"], "pc": _fmt_pc(bot["agg"]),
                 "tone": "up" if bot["agg"] >= 0 else "down"}),
        "gainers": [_mover(t, g_max) for t in gainers],
        "losers": [_mover(t, l_max) for t in losers],
        "sectors": [{
            "en": s["en"], "zh": s["zh"], "pc": _fmt_pc(s["agg"]),
            "up": s["agg"] >= 0,
            "w": round(max(4.0, abs(s["agg"]) / s_max * 100.0) if s_max > 0 else 0.0),
        } for s in secs],
    }


def sibling_markets(market: str) -> dict[str, str] | None:
    """"Hong Kong and Canada" — the OTHER two maps, named for the CTA copy.

    Computed from PAGE_META so one string serves three pages and a fourth market
    joins without a copy edit.
    """
    others = [k for k in PAGE_META if k != market]
    if not others:
        return None
    names = {
        "china": {"en": "China", "zh": "A股"},
        "hk": {"en": "Hong Kong", "zh": "港股"},
        "canada": {"en": "Canada", "zh": "加拿大"},
    }
    en = [names.get(k, {}).get("en", k) for k in others]
    zh = [names.get(k, {}).get("zh", k) for k in others]
    return {
        "en": " and ".join([", ".join(en[:-1]), en[-1]]) if len(en) > 1 else en[0],
        "zh": "与".join(zh) if len(zh) > 1 else zh[0],
    }
