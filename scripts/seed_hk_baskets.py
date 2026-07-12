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

COPY CONTRACT: this script regenerates the live file WHOLESALE, so edits made directly to
data/baskets_hk/membership.json (copy lanes, spliced baskets) survive a re-run only if they
are mirrored in the dicts below. Reconciled 2026-07-12 (2026-07-05 copy-simplification pass
backported); verify with a regen + diff before shipping seeder changes.
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

# COPY SYNC: name/thesis/*_zh here and CONSTRUCTION/HISTORY_NOTE/NOTE below must match the
# live data/baskets_hk/membership.json — this seeder regenerates it WHOLESALE, so copy edits
# made directly to the live file are clobbered on the next run unless mirrored here.
BASKETS: dict[str, dict] = {
    # ───────────────────────── Tech & Internet · 科技与互联网 ─────────────────────────
    "hk_china_tech": {
        "name": "China Tech & Internet", "name_zh": "中资科技与互联网",
        "category": "Tech & Internet", "category_zh": "科技与互联网",
        "etf_proxy": "3033.HK", "etf_proxy_note": "HS TECH ETF",
        "thesis": "HK-listed China internet, platform and hardware leaders. Core read on index growth and southbound tech flows.",
        "thesis_zh": "香港上市的中国互联网、平台和硬件龙头。观察指数成长股和南向科技资金。",
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
        "thesis": "Sportswear, catering, jewellery, beer, dairy and packaged food names. Tracks mainland consumer demand.",
        "thesis_zh": "运动服饰、餐饮、珠宝、啤酒、乳制品和食品公司。跟踪内地消费需求。",
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
        "thesis": "Innovative drug, CRO/CDMO and healthcare distributors. Tracks biotech funding and licensing momentum.",
        "thesis_zh": "创新药、CRO/CDMO 和医药分销商。跟踪生物科技融资和授权交易。",
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
        "thesis": "China NEV makers, smart-EV startups and auto suppliers listed in Hong Kong.",
        "thesis_zh": "在港上市的中国新能源车、智能电动车和汽车供应链公司。",
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
        "thesis": "Mainland state banks plus HSBC and BOCHK. Core southbound dividend and credit sleeve.",
        "thesis_zh": "内地国有银行加汇丰和中银香港。南向高股息和信贷核心板块。",
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
        "thesis": "AIA and mainland life/P&C insurers. Sensitive to markets, yields and new-business value.",
        "thesis_zh": "友邦和内地寿险/财险公司。受市场、利率和新业务价值影响。",
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
        "thesis": "HK conglomerates and HKEX. Barometer for local financial-hub activity and market turnover.",
        "thesis_zh": "香港综合企业和港交所。观察本地金融中心活跃度和市场成交。",
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
        "thesis": "HK developers, mainland landlords and Link REIT. Rate-sensitive property cycle exposure.",
        "thesis_zh": "香港地产商、内地物业公司和领展。利率敏感的地产周期敞口。",
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
        "thesis": "Macau casino concessionaires. High-beta read on gaming revenue and outbound travel.",
        "thesis_zh": "澳门博彩牌照公司。高贝塔反映博彩收入和出境旅游。",
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
        "thesis": "H-share oil, gas and coal majors. Dividend-heavy SOE exposure to energy prices and demand.",
        "thesis_zh": "H 股石油、天然气和煤炭龙头。高股息央企，受能源价格和需求影响。",
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
        "thesis": "H-share aluminium, copper and molybdenum producers. Cyclical commodity beta.",
        "thesis_zh": "H 股铝、铜和钼生产商。周期性商品贝塔。",
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
        "thesis": "Mainland telecoms plus HK utilities and infrastructure. Defensive, high-payout cash flows.",
        "thesis_zh": "内地电信加香港公用事业和基建。防御性、高派息现金流。",
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
        "thesis": "High-yield HK mega-caps across banks, telecom, energy and utilities.",
        "thesis_zh": "银行、电信、能源和公用事业中的高息港股大盘股。",
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

CURATED = "2026-06-18"   # member-expansion pass (deep cache widened 73 → ~157 HK names)

# ── 2026-06-18 expansion: on-thesis adds now that the hk_search deep cache covers the full
# ~157-name HKEX constituent set (was 73). bid -> [(ticker, rationale)]; validated like the rest.
EXPANSION: dict[str, list[tuple[str, str]]] = {
    "hk_china_tech": [
        ("9999.HK", "NetEase — gaming + music; the #2 China game publisher"),
        ("9626.HK", "Bilibili — Gen-Z video community + games"),
        ("9698.HK", "GDS Holdings — China data-center / AI capacity"),
        ("2382.HK", "Sunny Optical — smartphone + auto optics leader"),
        ("0285.HK", "BYD Electronic — handset/EV electronics assembly"),
        ("3888.HK", "Kingsoft — office software (WPS) + games + cloud"),
        ("0268.HK", "Kingdee — enterprise SaaS / cloud ERP"),
        ("1347.HK", "Hua Hong Semiconductor — mature-node foundry"),
        ("0763.HK", "ZTE — telecom equipment + 5G/networking"),
        ("0772.HK", "China Literature — online literature / IP (Tencent)"),
    ],
    "hk_consumer": [
        ("9633.HK", "Nongfu Spring — #1 bottled water + beverages"),
        ("0322.HK", "Tingyi — instant noodles + beverages (Master Kong)"),
        ("0151.HK", "Want Want — rice crackers / dairy snacks"),
        ("0345.HK", "Vitasoy — soy/plant beverages"),
        ("2313.HK", "Shenzhou International — knitwear OEM (Nike/Adidas)"),
        ("1112.HK", "Health & Happiness — infant formula / supplements"),
        ("6969.HK", "Smoore — global vaping device ODM"),
        ("9961.HK", "Trip.com — China online-travel leader"),
        ("6808.HK", "Sun Art Retail — hypermarket / grocery"),
    ],
    "hk_biotech": [
        ("1801.HK", "Innovent — PD-1 / oncology innovator"),
        ("9926.HK", "Akeso — bispecific antibody platform (ivonescimab)"),
        ("3692.HK", "Hansoh Pharma — innovative oncology/CNS"),
        ("2392.HK", "Pharmaron — CRO/CDMO across modalities"),
        ("2607.HK", "Shanghai Henlius — biosimilars + biologics"),
        ("6618.HK", "JD Health — online pharmacy / healthcare platform"),
        ("0867.HK", "China Medical System — specialty pharma distribution"),
        ("2196.HK", "Shanghai Pharmaceuticals — pharma distribution + manufacturing"),
        ("1066.HK", "Shandong Weigao — medical devices / consumables"),
    ],
    "hk_ev": [
        ("9863.HK", "Leapmotor — value smart-EV scaler (Stellantis-backed)"),
        ("2333.HK", "Great Wall Motor — SUV/pickup OEM + NEV/export"),
        ("1958.HK", "BAIC Motor — legacy OEM + premium JV"),
    ],
    "hk_banks": [
        ("3968.HK", "China Merchants Bank — premier retail bank (H)"),
        ("1658.HK", "Postal Savings Bank — vast retail deposit franchise (H)"),
        ("0998.HK", "CITIC Bank — national joint-stock lender (H)"),
        ("6818.HK", "China Everbright Bank (H)"),
        ("3618.HK", "Chongqing Rural Commercial Bank (H)"),
        ("2888.HK", "Standard Chartered — EM/Asia-focused global bank"),
    ],
    "hk_insurers": [
        ("1336.HK", "New China Life — mainland life insurer (H)"),
        ("2378.HK", "Prudential — pan-Asia/Africa life franchise"),
        ("6060.HK", "ZhongAn Online — digital P&C insurer"),
    ],
    "hk_conglo": [
        ("0656.HK", "Fosun International — diversified investment conglomerate"),
        ("0392.HK", "Beijing Enterprises — gas / infrastructure conglomerate"),
    ],
    "hk_property": [
        ("1113.HK", "CK Asset — the flagship HK developer/landlord"),
        ("0960.HK", "Longfor — quality mainland developer (H)"),
        ("1209.HK", "CR Mixc — asset-light mall/property management"),
        ("0101.HK", "Hang Lung Properties — HK + mainland malls"),
        ("0014.HK", "Hysan Development — Causeway Bay landlord"),
        ("0683.HK", "Kerry Properties — HK/mainland developer"),
        ("0778.HK", "Fortune REIT — HK suburban retail REIT"),
    ],
    "hk_gaming": [
        ("0200.HK", "Melco International — Macau/Cotai casino operator"),
    ],
    "hk_energy": [
        ("0902.HK", "Huaneng Power — large IPP / thermal power (H)"),
        ("1816.HK", "CGN Power — nuclear generation leader (H)"),
        ("1898.HK", "China Coal Energy — integrated coal (H)"),
        ("2883.HK", "China Oilfield Services — offshore oil services (H)"),
        ("0135.HK", "Kunlun Energy — natural-gas distribution (PetroChina)"),
    ],
    "hk_materials": [
        ("2899.HK", "Zijin Mining — global gold + copper major (H)"),
        ("1208.HK", "MMG — copper / zinc (Las Bambas)"),
        ("0323.HK", "Maanshan Iron & Steel (H)"),
        ("0639.HK", "Shougang Resources — coking coal"),
        ("1799.HK", "Xinte Energy — polysilicon / solar materials"),
        ("3800.HK", "GCL Technology — polysilicon for solar"),
    ],
    "hk_telco_util": [
        ("0836.HK", "China Resources Power — IPP + renewables (H)"),
        ("2688.HK", "ENN Energy — city-gas distribution"),
        ("0257.HK", "China Everbright Environment — waste-to-energy"),
        ("0371.HK", "Beijing Enterprises Water — water treatment"),
    ],
}

# wholly new basket created in the same pass (the HKEX industrial/infra cluster had no home)
NEW_BASKETS: dict[str, dict] = {
    "hk_industrials": {
        "name": "Industrials & Infrastructure", "name_zh": "工业与基建",
        "category": "Industrials & Transport", "category_zh": "工业与运输",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Industrial, infrastructure, rail, machinery and logistics names tied to capex and China growth.",
        "thesis_zh": "工业、基建、铁路、机械和物流公司，受资本开支和中国增长影响。",
        "members": [
            ("0669.HK", "Techtronic — global power tools (Milwaukee/Ryobi)"),
            ("1766.HK", "CRRC — the rolling-stock / rail-equipment giant (H)"),
            ("2338.HK", "Weichai Power — diesel engines / heavy-duty powertrains (H)"),
            ("0390.HK", "China Railway Group — construction SOE (H)"),
            ("1186.HK", "China Railway Construction — infra construction SOE (H)"),
            ("1072.HK", "Dongfang Electric — power-generation equipment (H)"),
            ("0144.HK", "China Merchants Port — port operator"),
            ("0316.HK", "Orient Overseas (OOIL) — container shipping"),
            ("2057.HK", "ZTO Express — China express-delivery leader"),
        ],
    },
}

CURATED2 = "2026-07-12"   # factor-split pass — sub-basket lenses (see SPLIT_BASKETS)

# ── 2026-07-12 factor-split lenses. The 2026-07 turn showed hk_china_tech blending two
# factors that decorrelate hard (10d spread +11.5% platforms vs −3.9% hardware; the split
# survives HSI-residualization [gap 0.16/120d] and split-half stability), and hk_materials
# blending diversified miners (within-corr 0.69) with steel/coal/solar names (0.26).
# These SUB-BASKETS are ADDITIVE lenses: the umbrellas stay unchanged for series/ledger
# continuity; sub-baskets share the umbrella's category so the allocation book's
# MAX_PER_PARENT de-overlap can never hold both an umbrella and its split.
SPLIT_BASKETS: dict[str, dict] = {
    "hk_platform_tech": {
        "name": "China Platform Megacaps", "name_zh": "中资平台科技龙头",
        "category": "Tech & Internet", "category_zh": "科技与互联网",
        "etf_proxy": "3033.HK", "etf_proxy_note": "HS TECH ETF — closest proxy; the index also carries hardware names",
        "thesis": "The consumer-internet platform megacaps split out of the China Tech umbrella — the names that share one re-rating factor (domestic consumption, AI application, southbound flow) and lead HK turns. Xiaomi rides here by behavior: it trades with the platform factor, not the hardware one.",
        "thesis_zh": "从中资科技伞篮拆出的消费互联网平台龙头 — 共享同一重估因子（内需、AI 应用、南向资金）并引领港股拐点的成员。小米按行为归入此篮：其走势跟随平台因子而非硬件因子。",
        "members": [
            ("0700.HK", "Tencent — gaming + WeChat super-app + cloud"),
            ("9988.HK", "Alibaba — e-commerce + cloud + AI"),
            ("3690.HK", "Meituan — local-services / food-delivery leader"),
            ("9618.HK", "JD.com — self-operated e-commerce + logistics"),
            ("9888.HK", "Baidu — search + AI / autonomous driving"),
            ("1024.HK", "Kuaishou — short-video + live commerce"),
            ("9999.HK", "NetEase — gaming + music; the #2 China game publisher"),
            ("9626.HK", "Bilibili — Gen-Z video community + games"),
            ("1810.HK", "Xiaomi — devices + EV; trades with the platform-megacap factor"),
        ],
    },
    "hk_tech_hardware": {
        "name": "Tech Hardware & Semis", "name_zh": "科技硬件与半导体",
        "category": "Tech & Internet", "category_zh": "科技与互联网",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The hardware half of the China Tech umbrella — foundries, telecom equipment and device supply chain. Driven by semiconductor capex, device demand and export controls, a distinctly different clock from the platform re-rating cycle.",
        "thesis_zh": "中资科技伞篮的硬件一侧 — 代工、通信设备与终端供应链。受半导体资本开支、终端需求与出口管制驱动，与平台重估周期明显不同步。",
        "members": [
            ("0981.HK", "SMIC — the mainland foundry champion"),
            ("1347.HK", "Hua Hong Semiconductor — mature-node foundry"),
            ("0763.HK", "ZTE — telecom equipment + 5G/networking"),
            ("0992.HK", "Lenovo — global PC + AI servers"),
            ("2382.HK", "Sunny Optical — smartphone + auto optics leader"),
            ("0285.HK", "BYD Electronic — handset/EV electronics assembly"),
        ],
    },
    "hk_miners": {
        "name": "Diversified Miners", "name_zh": "多元化矿业龙头",
        "category": "Energy & Resources", "category_zh": "能源与资源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The large diversified miners split out of Materials & Metals — copper, gold, aluminium and molybdenum majors that move on one global-metals factor (within-corr 0.69 vs 0.26 for the umbrella's steel/coal/solar tail).",
        "thesis_zh": "从有色金属伞篮拆出的大型多元化矿业 — 铜、金、铝与钼龙头，跟随单一全球金属因子（组内相关 0.69，而伞篮的钢铁/煤炭/光伏尾部仅 0.26）。",
        "members": [
            ("2600.HK", "Aluminum Corp of China (Chalco) — aluminium (H)"),
            ("0358.HK", "Jiangxi Copper — copper smelting + mining (H)"),
            ("1378.HK", "China Hongqiao — aluminium smelting leader"),
            ("3993.HK", "CMOC Group — molybdenum + copper/cobalt (H)"),
            ("2899.HK", "Zijin Mining — global gold + copper major (H)"),
            ("1208.HK", "MMG — copper / zinc (Las Bambas)"),
        ],
    },
}

CONSTRUCTION = "Equal-weight baskets, rebalanced monthly, measured against the Hang Seng Index."
HISTORY_NOTE = ("Available history comes from the hk_search cache. Pre-launch series use the "
                "basket's starting membership.")
NOTE = "Curated HK theme baskets for monitoring rotation. Descriptive only, not a buy list."


def main() -> int:
    con = pd.read_parquet(config.data_dir() / "hk_breadth" / "constituents.parquet")
    closes = pd.read_parquet(config.data_dir() / "hk_search" / "closes_deep.parquet")
    cols = set(closes.columns)

    # fold the 2026-06-18 expansion into the base definitions before materialising
    baskets = {**BASKETS, **NEW_BASKETS, **SPLIT_BASKETS}
    for bid, adds in EXPANSION.items():
        baskets[bid]["members"] = list(baskets[bid]["members"]) + list(adds)

    def en_name(t: str) -> str:
        if t in con.index:
            return str(con.loc[t, "name"])
        return t

    out_baskets, missing = {}, []
    for bid, b in baskets.items():
        members = []
        for ticker, rationale in b["members"]:
            if ticker not in cols:
                missing.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name": en_name(ticker), "rationale": rationale})
        if bid in SPLIT_BASKETS:
            src = "hk_china_tech" if b["category"] == "Tech & Internet" else "hk_materials"
            cl = [{"date": CURATED2, "action": "create",
                   "note": (f"Created {b['name']} — {len(members)} members split out of {src} as a "
                            "factor lens (correlation-audited 2026-07-12); umbrella retained unchanged.")}]
        elif bid in NEW_BASKETS:
            cl = [{"date": CURATED, "action": "create",
                   "note": f"Created {b['name']} — {len(members)} equal-weight HK members."}]
        else:
            cl = [{"date": SEED, "action": "create",
                   "note": f"Seeded {b['name']} — equal-weight HK members."}]
            if bid in EXPANSION:
                cl.append({"date": CURATED, "action": "expand",
                           "note": f"Expanded to {len(members)} members (deep cache widened to ~157 HK names)."})
        out_baskets[bid] = {
            "name": b["name"], "name_zh": b["name_zh"],
            "category": b["category"], "category_zh": b["category_zh"],
            "etf_proxy": b["etf_proxy"], "etf_proxy_note": b["etf_proxy_note"],
            "created": SEED, "weighting": "equal",
            "thesis": b["thesis"], "thesis_zh": b["thesis_zh"], "members": members,
            "changelog": cl,
        }

    if missing:
        log.error("TICKERS NOT IN hk_search cache (fix before shipping): %s", ", ".join(missing))
        return 1

    # cross-reference the split lenses on the umbrellas they were carved from
    for bid, sub_note in [("hk_china_tech", "hk_platform_tech / hk_tech_hardware"),
                          ("hk_materials", "hk_miners")]:
        out_baskets[bid]["changelog"].append(
            {"date": CURATED2, "action": "note",
             "note": f"Factor-split lenses created from this umbrella ({sub_note}); "
                     "umbrella membership unchanged for series continuity."})

    payload = {
        "version": CURATED2, "seed_date": SEED, "curated": CURATED2,
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
