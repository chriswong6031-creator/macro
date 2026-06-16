"""Seed data/baskets_hk/membership.json — curated Hong Kong thematic baskets.

The HK analogue of scripts/seed_china_baskets.py. Defines the recognizable HKEX themes —
China internet platforms, H-share + HK banks, insurers (AIA), Macau gaming, biotech/CXO,
China EV, HK property & REITs, H-share energy/materials, telecom/utilities and the
southbound high-dividend trade — and their equal-weight member tickers, then materialises
the membership schema engine.baskets_hk.compute_hk_baskets() consumes.

Member English names are filled from data/hk_breadth/constituents.parquet, and EVERY ticker
is validated against the hk_search deep close cache (fail loud on a miss). Benchmark = the
Hang Seng Index (HSI). Re-runnable: `python -m scripts.seed_hk_baskets`.

HONEST BY CONSTRUCTION: membership is curated today with knowledge of the period, so the
~5y series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest, not a buy list.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_hk_baskets")

SEED = "2021-06-15"

BASKETS: dict[str, dict] = {
    # ───────────────────────── Tech & Internet · 科技与互联网 ─────────────────────────
    "hk_china_tech": {
        "name": "China Tech & Internet", "name_zh": "中资科技与互联网",
        "category": "Tech & Internet", "category_zh": "科技与互联网",
        "etf_proxy": "3033.HK", "etf_proxy_note": "HS TECH ETF",
        "thesis": "The mega-cap China internet & hardware complex that dominates the Hang Seng — platforms, e-commerce, devices and the domestic foundry. The single biggest driver of HK index returns and the core southbound-flow target; levered to China consumption, AI capex and regulatory sentiment.",
        "thesis_zh": "主导恒指的中资互联网与硬件巨头 — 平台、电商、终端与本土代工。香港指数回报的最大驱动力，也是南向资金的核心标的；受中国消费、AI 资本开支与监管情绪牵动。",
        "members": [
            ("0700.HK", "Tencent — gaming + WeChat super-app + cloud"),
            ("9988.HK", "Alibaba — e-commerce + cloud + AI"),
            ("3690.HK", "Meituan — local-services / food-delivery leader"),
            ("9618.HK", "JD.com — self-operated e-commerce + logistics"),
            ("1810.HK", "Xiaomi — smartphones + IoT + EV"),
            ("9888.HK", "Baidu — search + AI / autonomous driving"),
            ("1024.HK", "Kuaishou — short-video + live commerce"),
            ("0992.HK", "Lenovo — global PC + AI servers"),
            ("0981.HK", "SMIC — the mainland foundry champion"),
        ],
    },
    # ─────────────────────── Consumer & Healthcare · 消费与医药 ───────────────────────
    "hk_consumer": {
        "name": "China Consumer Brands", "name_zh": "中资消费品牌",
        "category": "Consumer & Healthcare", "category_zh": "消费与医药",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "HK-listed China consumer champions — sportswear, catering, jewellery, beer, dairy and packaged food. A direct read on mainland discretionary demand and premiumisation, and a favourite southbound consumption basket.",
        "thesis_zh": "港股中资消费龙头 — 运动服饰、餐饮、珠宝、啤酒、乳业与包装食品。直接反映内地可选消费需求与升级趋势，也是南向资金偏好的消费篮子。",
        "members": [
            ("2020.HK", "Anta Sports — #1 China sportswear group"),
            ("2331.HK", "Li Ning — premium domestic sportswear"),
            ("1929.HK", "Chow Tai Fook — gold jewellery leader"),
            ("6862.HK", "Haidilao — hotpot catering chain"),
            ("0291.HK", "China Resources Beer — Snow/Heineken China"),
            ("0288.HK", "WH Group — global pork / packaged meat"),
            ("2319.HK", "Mengniu Dairy — #2 dairy"),
            ("1044.HK", "Hengan — tissue / personal care"),
        ],
    },
    "hk_biotech": {
        "name": "Biotech, Pharma & CXO", "name_zh": "生物医药与CXO",
        "category": "Consumer & Healthcare", "category_zh": "消费与医药",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The HK healthcare complex — innovative-drug developers, the CRO/CDMO outsourcing chain and the big distributors. The R&D-and-out-licensing growth engine, levered to biotech funding cycles, overseas BD deals and the 18A pipeline.",
        "thesis_zh": "港股医药板块 — 创新药企、CRO/CDMO 外包链与大型流通商。研发与对外授权的成长引擎，受生物科技融资周期、海外 BD 交易与 18A 管线驱动。",
        "members": [
            ("1093.HK", "CSPC Pharma — branded generics + innovation"),
            ("1177.HK", "Sino Biopharm — large innovative-drug pipeline"),
            ("2269.HK", "WuXi Biologics — biologics CDMO leader"),
            ("2359.HK", "WuXi AppTec — the CXO bellwether"),
            ("6160.HK", "BeiGene — global oncology biotech"),
            ("1099.HK", "Sinopharm — pharma distribution giant"),
        ],
    },
    # ────────────────────────────── Autos & EV · 汽车 ──────────────────────────────
    "hk_ev": {
        "name": "China EV & Autos", "name_zh": "中资电动车",
        "category": "Autos & EV", "category_zh": "汽车",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The HK-listed China auto transition — the NEV scale leader, the smart-EV start-ups and the legacy OEMs reinventing for electrification and export. A high-beta play on EV penetration, price competition and the overseas push.",
        "thesis_zh": "港股中资汽车电动化 — 新能源车规模龙头、智能电动车新势力与转型出海的传统车企。受电动化渗透、价格战与出海驱动的高弹性主题。",
        "members": [
            ("1211.HK", "BYD — the NEV scale + export leader"),
            ("2015.HK", "Li Auto — EREV premium SUVs"),
            ("9868.HK", "XPeng — smart-EV / ADAS"),
            ("0175.HK", "Geely — legacy OEM + Zeekr NEV"),
            ("2238.HK", "Guangzhou Auto — JV + Aion NEV"),
        ],
    },
    # ─────────────────────────────── Financials · 金融 ───────────────────────────────
    "hk_banks": {
        "name": "Banks (H + HK)", "name_zh": "银行",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The banking complex listed in HK — the big mainland state lenders (H-shares) alongside HSBC and BOC Hong Kong. The core of the southbound high-dividend trade and a direct read on China credit, net-interest-margin and HK rates.",
        "thesis_zh": "在港上市的银行 — 内地国有大行（H 股）加汇丰与中银香港。南向高股息交易的核心，也是中国信用、净息差与香港利率的直接读数。",
        "members": [
            ("1398.HK", "ICBC — largest state bank (H)"),
            ("0939.HK", "China Construction Bank (H)"),
            ("3988.HK", "Bank of China (H)"),
            ("3328.HK", "Bank of Communications (H)"),
            ("1288.HK", "Agricultural Bank of China (H)"),
            ("0005.HK", "HSBC — global bank, HK anchor"),
            ("2388.HK", "BOC Hong Kong — HK retail/clearing bank"),
        ],
    },
    "hk_insurers": {
        "name": "Insurers", "name_zh": "保险",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The big HK-listed insurers — AIA's pan-Asian life franchise plus the mainland life & P&C majors. Earnings and embedded value swing on equity markets, long-bond yields and new-business value; a leveraged play on an Asia risk-on turn.",
        "thesis_zh": "港股大型险企 — 友邦的泛亚寿险特许经营加内地寿险与财险龙头。利润与内含价值随权益市场、长债收益率与新业务价值波动；对亚洲风险偏好回升的杠杆化表达。",
        "members": [
            ("2318.HK", "Ping An — integrated insurance + fintech"),
            ("1299.HK", "AIA — pan-Asian life champion"),
            ("2628.HK", "China Life — largest mainland life (H)"),
            ("2601.HK", "China Pacific Insurance (H)"),
            ("0966.HK", "China Taiping — life + P&C"),
        ],
    },
    "hk_conglo": {
        "name": "Conglomerates & Exchange", "name_zh": "综合企业与交易所",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The old-economy HK hongs and the exchange operator — sprawling ports/retail/aviation conglomerates plus HKEX, whose earnings track market turnover, listings and southbound activity. A barometer of HK as a financial hub.",
        "thesis_zh": "香港老牌综合企业与交易所 — 横跨港口/零售/航空的多元集团，加上盈利挂钩成交、上市与南向活动的港交所。香港金融中心地位的晴雨表。",
        "members": [
            ("0001.HK", "CK Hutchison — ports / retail / telecom / infra"),
            ("0019.HK", "Swire Pacific — property / aviation / beverages"),
            ("0388.HK", "HKEX — the exchange operator"),
        ],
    },
    # ────────────────────────────── Property · 地产 ──────────────────────────────
    "hk_property": {
        "name": "Property & REITs", "name_zh": "地产与REITs",
        "category": "Property", "category_zh": "地产",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "HK & China property — the big HK developers, the mainland SOE landlords and Link REIT. Levered to HK rates and physical-market sentiment plus the China property cycle; a high-beta, rate-sensitive value sleeve.",
        "thesis_zh": "香港与内地地产 — 香港大型发展商、内地国有地产商与领展。受香港利率与楼市情绪及内地地产周期驱动；高弹性、对利率敏感的价值板块。",
        "members": [
            ("0016.HK", "Sun Hung Kai — the premier HK developer"),
            ("1109.HK", "China Resources Land — SOE landlord (H)"),
            ("0688.HK", "China Overseas Land — SOE developer (H)"),
            ("0823.HK", "Link REIT — Asia's largest REIT"),
            ("0017.HK", "New World Development"),
            ("1997.HK", "Wharf REIC — HK investment properties"),
            ("0012.HK", "Henderson Land"),
            ("0083.HK", "Sino Land"),
        ],
    },
    # ─────────────────────────── Gaming & Tourism · 博彩旅游 ───────────────────────────
    "hk_gaming": {
        "name": "Macau Gaming", "name_zh": "澳门博彩",
        "category": "Gaming & Tourism", "category_zh": "博彩旅游",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The Macau casino concessionaires — pure-play exposure to gross gaming revenue, mass-market recovery and Chinese outbound travel. A high-beta consumption-reopening basket distinct from the rest of HK.",
        "thesis_zh": "澳门博彩特许经营商 — 纯粹押注博彩毛收入、中场复苏与中国出境游。区别于其余港股的高弹性消费复苏篮子。",
        "members": [
            ("0027.HK", "Galaxy Entertainment — mass-market leader"),
            ("1928.HK", "Sands China — Cotai integrated resorts"),
            ("0880.HK", "SJM Holdings — Grand Lisboa"),
            ("2282.HK", "MGM China"),
        ],
    },
    # ─────────────────────── Energy & Resources · 能源与资源 ───────────────────────
    "hk_energy": {
        "name": "Energy (H-shares)", "name_zh": "能源",
        "category": "Energy & Resources", "category_zh": "能源与资源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The H-share energy majors — the three oil & gas giants plus the top thermal-coal producer. Heavy free-cash-flow, high payout SOEs at the centre of the southbound dividend trade; levered to oil, gas and power demand.",
        "thesis_zh": "H 股能源龙头 — 三桶油加动力煤龙头。现金流充沛、高分红的央企，处于南向红利交易核心；受油、气与电力需求驱动。",
        "members": [
            ("0883.HK", "CNOOC — low-cost offshore E&P"),
            ("0857.HK", "PetroChina — integrated oil & gas (H)"),
            ("0386.HK", "Sinopec — refining / chemicals (H)"),
            ("1088.HK", "China Shenhua — integrated coal/power (H)"),
            ("0934.HK", "Sinopec Kantons — oil logistics"),
        ],
    },
    "hk_materials": {
        "name": "Materials & Metals", "name_zh": "有色金属",
        "category": "Energy & Resources", "category_zh": "能源与资源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The H-share base & industrial-metals producers — aluminium, copper and molybdenum. A China-listed read on the global growth cycle, green-capex demand and supply discipline; a cyclical commodity beta sleeve.",
        "thesis_zh": "H 股基本金属与工业金属生产商 — 铝、铜与钼。表达全球增长周期、绿色资本开支需求与供给约束的中资读数；周期性大宗 Beta 板块。",
        "members": [
            ("2600.HK", "Aluminum Corp of China (Chalco)"),
            ("0358.HK", "Jiangxi Copper — copper leader"),
            ("1378.HK", "China Hongqiao — top aluminium"),
            ("3993.HK", "CMOC — copper / cobalt / moly"),
            ("0486.HK", "RUSAL — aluminium"),
        ],
    },
    # ──────────────────── Telecom, Utilities & Income · 电信公用与收息 ────────────────────
    "hk_telco_util": {
        "name": "Telecom & Utilities", "name_zh": "电信与公用事业",
        "category": "Telecom, Utilities & Income", "category_zh": "电信公用与收息",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The defensive carriers and HK utilities/infrastructure — the three mainland telecoms plus power, gas, infra and the mass-transit operator. Stable cash flows and high payouts; a low-beta, rate-sensitive defensive anchor.",
        "thesis_zh": "防御性运营商与香港公用/基建 — 三大内地电信加电力、燃气、基建与地铁运营商。现金流稳定、分红高；低 Beta、对利率敏感的防御锚。",
        "members": [
            ("0941.HK", "China Mobile — carrier + dividend anchor"),
            ("0762.HK", "China Unicom"),
            ("0728.HK", "China Telecom"),
            ("0002.HK", "CLP Holdings — HK power utility"),
            ("0003.HK", "HK & China Gas (Towngas)"),
            ("0006.HK", "Power Assets Holdings"),
            ("1038.HK", "CK Infrastructure"),
            ("0066.HK", "MTR Corporation — rail + property"),
        ],
    },
    "hk_dividend": {
        "name": "High-Dividend Blue Chips", "name_zh": "高股息蓝筹",
        "category": "Telecom, Utilities & Income", "category_zh": "电信公用与收息",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "A southbound-income blend — the highest-yielding HK mega-caps across banks, telecom, energy and utilities. Built to express the dividend/value factor that has led HK leadership; income with cyclical tail risk, overlaps the sector baskets by design.",
        "thesis_zh": "南向收息组合 — 横跨银行、电信、能源与公用事业的高股息超大盘。用于表达引领港股的红利/价值因子；高股息但有周期尾部风险，与行业篮子刻意重叠。",
        "members": [
            ("0005.HK", "HSBC — global bank, high payout"),
            ("0941.HK", "China Mobile — carrier dividend"),
            ("0883.HK", "CNOOC — energy free-cash-flow"),
            ("0002.HK", "CLP Holdings — utility yield"),
            ("0006.HK", "Power Assets — utility yield"),
            ("0003.HK", "HK & China Gas"),
            ("1088.HK", "China Shenhua — coal/power dividend"),
            ("0386.HK", "Sinopec — refining dividend"),
        ],
    },
}

CONSTRUCTION = ("Equal-weighted, monthly-rebalanced, buy-and-hold between rebalances; dated "
                "membership changes take effect same-day. Benchmark = Hang Seng Index (HSI).")
HISTORY_NOTE = ("Series before a basket's creation date are a backtest of the membership as of "
                "creation; live tracking starts at creation. Universe = the HK search deep cache "
                "(HSI/HSCEI names), trimmed to a ~5y window.")
NOTE = ("Curated HK thematic baskets — hindsight-curated and descriptive, not an out-of-sample "
        "backtest and not a buy list.")


def main() -> int:
    con = pd.read_parquet(config.data_dir() / "hk_breadth" / "constituents.parquet")
    closes = pd.read_parquet(config.data_dir() / "hk_search" / "closes_deep.parquet")
    cols = set(closes.columns)

    def en_name(t: str) -> str:
        if t in con.index:
            return str(con.loc[t, "name"])
        return t

    out_baskets, missing = {}, []
    for bid, b in BASKETS.items():
        members = []
        for ticker, rationale in b["members"]:
            if ticker not in cols:
                missing.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name": en_name(ticker), "rationale": rationale})
        out_baskets[bid] = {
            "name": b["name"], "name_zh": b["name_zh"],
            "category": b["category"], "category_zh": b["category_zh"],
            "etf_proxy": b["etf_proxy"], "etf_proxy_note": b["etf_proxy_note"],
            "created": SEED, "weighting": "equal",
            "thesis": b["thesis"], "thesis_zh": b["thesis_zh"], "members": members,
            "changelog": [{"date": SEED, "action": "create",
                           "note": f"Seeded {b['name']} — {len(members)} equal-weight HK members."}],
        }

    if missing:
        log.error("TICKERS NOT IN hk_search cache (fix before shipping): %s", ", ".join(missing))
        return 1

    payload = {
        "version": SEED, "seed_date": SEED, "curated": SEED,
        "benchmark": "_HSI", "benchmark_label": "HSI", "benchmark_label_zh": "恒生指数",
        "construction": CONSTRUCTION, "history_note": HISTORY_NOTE, "note": NOTE,
        "baskets": out_baskets,
    }
    out_dir = config.data_dir() / "baskets_hk"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "membership.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d baskets, %d members, all tickers validated against hk_search",
             out_dir / "membership.json", len(out_baskets), n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
