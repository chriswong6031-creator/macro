"""Seed data/baskets_china/membership.json — curated A-share thematic baskets.

The China analogue of data/baskets/membership.json. Defines recognizable A-share
themes (白酒 baijiu, 半导体 semis, AI 算力 compute, 锂电 battery, 中特估 SOE value …)
and their equal-weight member tickers, then materialises the same membership schema
engine.baskets_china.compute_china_baskets() consumes.

Authoring contract: here we hand-curate only (ticker, English rationale) per member
plus the bilingual theme name / thesis / ETF proxy. The member's Chinese name is filled
from data/china_search/members.parquet, and EVERY ticker is validated against the
china_search close cache (fail loud if any is absent) so the page never silently drops a
member — except tickers in the REMOVED registry below, which re-encode the nightly
reconciler's dated prunes (scripts/reconcile_membership.py) so a regen reproduces the live
file. Re-runnable: `python -m scripts.seed_china_baskets`.

HONEST BY CONSTRUCTION (house rule, identical to the US baskets): membership is curated
today with knowledge of the period, so the ~5y series is HINDSIGHT-curated and
descriptive — not an out-of-sample backtest and not a buy list. Universe = the free
china_search top-mktcap A-share cache; names that begin trading mid-window are flagged
`partial` by the engine. Benchmark = CSI 300 (沪深300, the 510300.SS ETF).
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
log = logging.getLogger("seed_china_baskets")

SEED = "2021-06-15"   # start of the free china_search cache; members seeded here, late-listers auto-flagged partial

# Each basket: id -> dict(name, name_zh, category, category_zh, etf_proxy, etf_proxy_note,
#                          thesis, thesis_zh, members=[(ticker, rationale_en), ...])
BASKETS: dict[str, dict] = {
    # ───────────────────────── 科技与AI · Technology & AI ─────────────────────────
    "cn_semis": {
        "name": "Semiconductors", "name_zh": "半导体",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "512760.SS", "etf_proxy_note": "半导体ETF — chip-localization basket",
        "thesis": "China chip-localization names across foundry, equipment, design and memory.",
        "thesis_zh": "中国芯片国产化公司，覆盖晶圆代工、设备、设计和存储。",
        "members": [
            ("688981.SS", "SMIC — the flagship foundry; the core of mainland capacity"),
            ("688256.SS", "Cambricon — domestic AI accelerator; the NVDA-alternative bet"),
            ("002371.SZ", "NAURA — leading semiconductor equipment (etch/deposition)"),
            ("688041.SS", "Hygon — x86 server CPUs / DCU compute"),
            ("688347.SS", "Hua Hong — mature-node specialty foundry"),
            ("603986.SS", "GigaDevice — NOR flash + MCU design leader"),
            ("688012.SS", "AMEC — etch-tool champion (中微公司)"),
            ("688008.SS", "Montage — interface/memory-buffer chips (DDR5 cycle)"),
            ("300782.SZ", "Maxscend — RF front-end modules (卓胜微)"),
            ("002049.SZ", "Unigroup Guoxin — FPGA / special-purpose ICs"),
            ("688082.SS", "ACM Research Shanghai — cleaning / plating equipment (盛美上海)"),
            ("688072.SS", "Piotech — thin-film deposition (PECVD) equipment (拓荆科技)"),
            ("688120.SS", "Hwatsing — CMP polishing equipment (华海清科)"),
            ("688126.SS", "NSIG — 300mm silicon-wafer leader (沪硅产业)"),
            ("600584.SS", "JCET — #1 OSAT advanced packaging (长电科技)"),
            ("002156.SZ", "Tongfu Micro — OSAT packaging, AMD JV (通富微电)"),
            ("600460.SS", "Silan Micro — power-semi IDM (士兰微)"),
            ("603501.SS", "Will Semi / OmniVision — CMOS image sensors (豪威集团)"),
            ("300661.SZ", "SG Micro — analog IC leader (圣邦股份)"),
            ("688385.SS", "Fudan Micro — FPGA + security ICs (复旦微电)"),
            ("688019.SS", "Anji Micro — CMP slurry / process materials (安集科技)"),
            ("688249.SS", "Nexchip — display-driver specialty foundry (晶合集成)"),
        ],
    },
    "cn_ai_compute": {
        "name": "AI Compute & Optics", "name_zh": "AI算力与光模块",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "Optics, AI servers, switches and domestic accelerators tied to China AI capex.",
        "thesis_zh": "光模块、AI 服务器、交换机和国产加速器，受中国 AI 资本开支影响。",
        "members": [
            ("300308.SZ", "Zhongji Innolight — global 800G optical-module leader (中际旭创)"),
            ("300502.SZ", "Eoptolink — 800G optics fast-follower (新易盛)"),
            ("601138.SS", "Foxconn Industrial Internet — AI-server ODM scale (工业富联)"),
            ("688256.SS", "Cambricon — domestic training/inference accelerator"),
            ("000977.SZ", "Inspur — China's #1 AI-server vendor (浪潮信息)"),
            ("300394.SZ", "TFC Optical — optical passives / components (天孚通信)"),
            ("002281.SZ", "Accelink — optical chips & modules (光迅科技)"),
            ("603019.SS", "Sugon — HPC / AI server + liquid cooling (中科曙光)"),
            ("688041.SS", "Hygon — DCU compute for domestic AI clusters"),
            ("688795.SS", "Moore Threads — domestic AI / GPU accelerator (摩尔线程)"),
            ("688802.SS", "MetaX — domestic GPGPU accelerator (沐曦股份)"),
            ("300476.SZ", "Victory Giant — high-layer-count AI / HDI PCB (胜宏科技)"),
            ("002463.SZ", "WUS Printed Circuit — AI-server PCB (沪电股份)"),
            ("300620.SZ", "Advanced Fiber Resources — LiNbO3 modulators for 1.6T optics (光库科技)"),
            ("300442.SZ", "Range Intelligent Computing — AI data-centre / IDC operator (润泽科技)"),
            ("688702.SS", "Centec — Ethernet switch silicon (盛科通信)"),
            ("002837.SZ", "Envicool — AI data-centre liquid cooling (英维克)"),
        ],
    },
    "cn_consumer_elec": {
        "name": "Consumer Electronics", "name_zh": "消费电子",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "Apple/Android supply-chain names tied to smartphones, AI devices and hardware upgrades.",
        "thesis_zh": "苹果和安卓供应链公司，受智能手机、AI 设备和硬件升级影响。",
        "members": [
            ("002475.SZ", "Luxshare — top precision-assembly / connectors (立讯精密)"),
            ("002241.SZ", "GoerTek — acoustics + AR/VR hardware (歌尔股份)"),
            ("300433.SZ", "Lens Technology — cover glass / casings (蓝思科技)"),
            ("000725.SZ", "BOE — the dominant display panel maker (京东方)"),
            ("002384.SZ", "Dongshan Precision — FPC / PCB (东山精密)"),
            ("002938.SZ", "Avary Holding — flex-PCB leader (鹏鼎控股)"),
            ("002600.SZ", "Lingyi iTech — functional parts / assembly (领益智造)"),
            ("002273.SZ", "Crystal-Optech — optical filters / imaging (水晶光电)"),
            ("002916.SZ", "Shennan Circuits — PCB + IC substrates (深南电路)"),
            ("000100.SZ", "TCL Technology — LCD / Mini-LED panels (TCL科技)"),
            ("002138.SZ", "Sunlord — inductors / passives (顺络电子)"),
            ("300136.SZ", "Sunway Communication — RF / antenna modules (信维通信)"),
            ("300866.SZ", "Anker Innovations — global consumer-electronics brand (安克创新)"),
            ("688036.SS", "Transsion — emerging-market handset OEM (传音控股)"),
            ("002456.SZ", "OFILM — camera modules (欧菲光)"),
        ],
    },
    "cn_software": {
        "name": "Software & AI Apps", "name_zh": "软件与AI应用",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Domestic software and AI application names tied to IT localization and generative AI demand.",
        "thesis_zh": "国产软件和 AI 应用公司，受 IT 国产化和生成式 AI 需求影响。",
        "members": [
            ("688111.SS", "Kingsoft Office — WPS suite + AI copilot (金山办公)"),
            ("002230.SZ", "iFlytek — speech & LLM platform (科大讯飞)"),
            ("600570.SS", "Hundsun — financial-institution software (恒生电子)"),
            ("300454.SZ", "Sangfor — security / cloud infrastructure (深信服)"),
            ("600845.SS", "Baosight — industrial software (宝信软件)"),
            ("300033.SZ", "Hithink RoyalFlush — retail fintech data (同花顺)"),
            ("300418.SZ", "Kunlun Tech — AIGC / overseas internet (昆仑万维)"),
            ("600588.SS", "Yonyou — enterprise ERP / cloud (用友网络)"),
            ("300496.SZ", "Thundersoft — edge-AI / OS / smart-cockpit software (中科创达)"),
            ("688692.SS", "Dameng — domestic database, 信创 (达梦数据)"),
            ("301236.SZ", "iSoftStone — IT services / 信创 integrator (软通动力)"),
            ("300339.SZ", "Hoperun — fintech software / HarmonyOS (润和软件)"),
            ("300803.SZ", "Compass — retail fintech terminal (指南针)"),
            ("301269.SZ", "Empyrean — domestic EDA software (华大九天)"),
            ("601360.SS", "Qihoo 360 — security + AI-model platform (三六零)"),
        ],
    },
    # ─────────────────────── 新能源与汽车 · New Energy & Autos ───────────────────────
    "cn_battery": {
        "name": "Battery & Lithium", "name_zh": "锂电池",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515030.SS", "etf_proxy_note": "新能源车ETF — battery-heavy",
        "thesis": "Lithium battery chain: cells, resources, materials and components. Driven by EV demand and lithium prices.",
        "thesis_zh": "锂电池产业链：电芯、资源、材料和零部件。受电动车需求和锂价影响。",
        "members": [
            ("300750.SZ", "CATL — the global cell champion (宁德时代)"),
            ("002594.SZ", "BYD — batteries + the EV scale leader (比亚迪)"),
            ("300014.SZ", "EVE Energy — cells + energy storage (亿纬锂能)"),
            ("002460.SZ", "Ganfeng Lithium — lithium resource / refining (赣锋锂业)"),
            ("002466.SZ", "Tianqi Lithium — lithium upstream (天齐锂业)"),
            ("300207.SZ", "Sunwoda — consumer + EV battery packs (欣旺达)"),
            ("002074.SZ", "Gotion High-tech — LFP cells (国轩高科)"),
            ("603659.SS", "Putailai — anode + coating equipment (璞泰来)"),
            ("002812.SZ", "Enjie — wet-process separator leader (恩捷股份)"),
            ("002709.SZ", "Tinci Materials — electrolyte leader (天赐材料)"),
            ("300037.SZ", "Capchem — electrolyte leader (新宙邦)"),
            ("300919.SZ", "CNGR — ternary precursor leader (中伟新材)"),
            ("300073.SZ", "Easpring — NCM cathode (当升科技)"),   # removed 2026-07-01 — see REMOVED
            ("301358.SZ", "Hunan Yuneng — LFP cathode leader (湖南裕能)"),
            ("603799.SS", "Huayou Cobalt — cobalt / nickel + precursors (华友钴业)"),
            ("002850.SZ", "Kedali — battery structural components (科达利)"),
            ("002340.SZ", "GEM — battery recycling / precursors (格林美)"),
        ],
    },
    "cn_solar": {
        "name": "Solar / Photovoltaics", "name_zh": "光伏",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515790.SS", "etf_proxy_note": "光伏ETF",
        "thesis": "Solar manufacturing chain from silicon to modules and inverters. Volume growth versus margin pressure.",
        "thesis_zh": "光伏制造链，从硅料到组件和逆变器。量增与利润率压力并存。",
        "members": [
            ("601012.SS", "LONGi — wafer + module leader (隆基绿能)"),
            ("600438.SS", "Tongwei — polysilicon + cells (通威股份)"),
            ("300274.SZ", "Sungrow — #1 inverter / storage (阳光电源)"),
            ("002129.SZ", "TCL Zhonghuan — silicon wafers (TCL中环)"),
            ("688223.SS", "Jinko Solar — top global module shipper (晶科能源)"),
            ("688303.SS", "Daqo — polysilicon pure-play (大全能源)"),
            ("603806.SS", "Foster — EVA encapsulant film leader (福斯特)"),
            ("688472.SS", "CSI Solar — modules + storage (阿特斯)"),
            ("688599.SS", "Trina Solar — global module shipper (天合光能)"),
            ("002459.SZ", "JA Solar — top module maker (晶澳科技)"),
            ("300763.SZ", "Ginlong Solis — string inverters (锦浪科技)"),
            ("688390.SS", "GoodWe — inverters + storage (固德威)"),
            ("605117.SS", "Deye — hybrid / micro-inverters + storage (德业股份)"),
            ("300316.SZ", "Jingsheng — crystal-growth equipment (晶盛机电)"),
            ("300751.SZ", "Maxwell — HJT cell-process equipment (迈为股份)"),
        ],
    },
    "cn_autos": {
        "name": "Autos & NEV Makers", "name_zh": "汽车整车",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515250.SS", "etf_proxy_note": "智能汽车ETF",
        "thesis": "China automakers and suppliers tied to EV adoption, intelligent driving and exports.",
        "thesis_zh": "中国整车和供应商，受电动车渗透、智能驾驶和出口影响。",
        "members": [
            ("002594.SZ", "BYD — the NEV scale + export leader (比亚迪)"),
            ("601633.SS", "Great Wall Motor — SUV/pickup + export (长城汽车)"),
            ("000625.SZ", "Changan — fast NEV transition (长安汽车)"),
            ("600104.SS", "SAIC Motor — largest legacy OEM (上汽集团)"),
            ("601127.SS", "Seres — Huawei AITO partner (赛力斯)"),
            ("601238.SS", "GAC Group — JV + Aion NEV (广汽集团)"),
            ("600660.SS", "Fuyao Glass — global auto-glass leader (福耀玻璃)"),
            ("601689.SS", "Tuopu — chassis + thermal, Tesla supplier (拓普集团)"),
            ("002920.SZ", "Desay SV — smart-cockpit / ADAS (德赛西威)"),
            ("000338.SZ", "Weichai Power — heavy-duty powertrain (潍柴动力)"),
            ("600741.SS", "Huayu Automotive — the largest parts group (华域汽车)"),
            ("601799.SS", "Xingyu — automotive lighting (星宇股份)"),
            ("002126.SZ", "Yinlun — thermal management (银轮股份)"),
            ("600066.SS", "Yutong Bus — buses + EV export (宇通客车)"),
            ("000800.SZ", "FAW Jiefang — heavy-truck OEM (一汽解放)"),
            ("600418.SS", "JAC — OEM, Huawei / NIO partner (江淮汽车)"),
        ],
    },
    # ─────────────────────── 高端制造 · Advanced Manufacturing ───────────────────────
    "cn_defense": {
        "name": "Defense & Aerospace", "name_zh": "军工航天",
        "category": "Advanced Manufacturing", "category_zh": "高端制造",
        "etf_proxy": "512660.SS", "etf_proxy_note": "军工ETF",
        "thesis": "Military and aerospace suppliers tied to modernization budgets and order books.",
        "thesis_zh": "军工和航空航天供应商，受现代化预算和订单影响。",
        "members": [
            ("600760.SS", "AVIC Shenyang — fighter-jet prime (中航沈飞)"),
            ("302132.SZ", "AVIC Chengdu — J-series fighters (中航成飞)"),
            ("600893.SS", "AECC Aviation Power — aero-engines (航发动力)"),
            ("000768.SZ", "AVIC Xi'an — bombers / transports (中航西飞)"),
            ("002179.SZ", "Jonhon — defense connectors (中航光电)"),
            ("600150.SS", "CSSC — shipbuilding champion (中国船舶)"),
            ("600118.SS", "China Spacesat — satellites (中国卫星)"),
            ("002414.SZ", "Guide Infrared — thermal imaging (高德红外)"),
            ("600372.SS", "AVIC Airborne Systems — avionics (中航机载)"),
            ("600879.SS", "Aerospace Times Electronics — missiles / electronics (航天电子)"),
            ("002025.SZ", "Guizhou Space Appliance — mil connectors (航天电器)"),
            ("688297.SS", "AVIC UAS — military drones (中无人机)"),
            ("600562.SS", "Glarun — defense radar (国睿科技)"),   # removed 2026-07-01 — see REMOVED
            ("000733.SZ", "China Zhenhua — military electronic components (振华科技)"),
        ],
    },
    "cn_robotics": {
        "name": "Robotics & Automation", "name_zh": "机器人与自动化",
        "category": "Advanced Manufacturing", "category_zh": "高端制造",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Automation and humanoid-robot supply chain: drives, reducers, controllers and parts.",
        "thesis_zh": "自动化和人形机器人供应链：驱动、减速器、控制器和零部件。",
        "members": [
            ("300124.SZ", "Inovance — servo / motion-control leader (汇川技术)"),
            ("688017.SS", "Leader Drive — harmonic reducers (绿的谐波)"),
            ("002747.SZ", "Estun — industrial robots (埃斯顿)"),
            ("300024.SZ", "Siasun — robotics pioneer (机器人/新松)"),
            ("002472.SZ", "Shuanghuan — precision gears / RV reducers (双环传动)"),
            ("002050.SZ", "Sanhua — thermal mgmt + humanoid actuators (三花智控)"),
            ("601689.SS", "Tuopu — humanoid linear-actuator supplier (拓普集团)"),
            ("601100.SS", "Hengli Hydraulic — actuators / electric cylinders (恒立液压)"),
            ("002046.SZ", "Sinomach Precision — high-precision bearings (国机精工)"),
            ("688322.SS", "Orbbec — 3D vision sensors for robots (奥比中光)"),
            ("002851.SZ", "Megmeet — motion / power-electronics control (麦格米特)"),
        ],
    },
    # ────────────────────────── 核心消费 · Consumer & Brands ──────────────────────────
    "cn_baijiu": {
        "name": "Baijiu / Liquor", "name_zh": "白酒",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": "512690.SS", "etf_proxy_note": "酒ETF",
        "thesis": "Premium liquor leaders. Read on Chinese premium consumption and confidence.",
        "thesis_zh": "高端白酒龙头。观察中国高端消费和信心。",
        "members": [
            ("600519.SS", "Kweichow Moutai — the ultra-premium anchor (贵州茅台)"),
            ("000858.SZ", "Wuliangye — the #2 premium brand (五粮液)"),
            ("000568.SZ", "Luzhou Laojiao — premium + mid-range (泸州老窖)"),
            ("600809.SS", "Shanxi Fenjiu — fast-growing fragrance baijiu (山西汾酒)"),
            ("002304.SZ", "Yanghe — east-China leader (洋河股份)"),
            ("000596.SZ", "Gujing Gong — regional premium (古井贡酒)"),
            ("603369.SS", "King's Luck — fast-growing Jiangsu baijiu (今世缘)"),
        ],
    },
    "cn_appliances": {
        "name": "Home Appliances", "name_zh": "家电",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "White-goods and appliance leaders tied to trade-in stimulus, exports and property after-cycle.",
        "thesis_zh": "白电和家电龙头，受以旧换新、出口和地产后周期影响。",
        "members": [
            ("000333.SZ", "Midea — diversified appliance + robotics (美的集团)"),
            ("000651.SZ", "Gree — air-conditioning leader (格力电器)"),
            ("600690.SS", "Haier Smart Home — global premium brands (海尔智家)"),
            ("000921.SZ", "Hisense Home Appliances — AC + white goods (海信家电)"),
            ("600060.SS", "Hisense Visual — TV / display (海信视像)"),
            ("002032.SZ", "Supor — small kitchen appliances (苏泊尔)"),
            ("603486.SS", "Ecovacs — robot vacuums / smart home (科沃斯)"),
            ("600839.SS", "Sichuan Changhong — TV + white goods (四川长虹)"),
        ],
    },
    "cn_food_bev": {
        "name": "Food & Beverage", "name_zh": "食品饮料",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": "159928.SZ", "etf_proxy_note": "消费ETF — staples",
        "thesis": "Staple food and beverage leaders. Defensive read on mass-market demand and input costs.",
        "thesis_zh": "大众食品饮料龙头。防御性观察大众需求和成本。",
        "members": [
            ("600887.SS", "Yili — the dairy leader (伊利股份)"),
            ("603288.SS", "Haitian — soy sauce / condiments king (海天味业)"),
            ("605499.SS", "Eastroc Beverage — energy-drink growth (东鹏饮料)"),
            ("300999.SZ", "Arawana — cooking oil / staples (金龙鱼)"),
            ("000895.SZ", "Shuanghui — meat processing leader (双汇发展)"),
            ("600600.SS", "Tsingtao Brewery — premium beer (青岛啤酒)"),
            ("000729.SZ", "Yanjing Brewery — beer (燕京啤酒)"),
            ("600298.SS", "Angel Yeast — yeast / food ingredients (安琪酵母)"),
            ("603345.SS", "Anjoy Foods — frozen prepared foods (安井食品)"),   # removed 2026-07-01 — see REMOVED
            ("603156.SS", "Yangyuan — Six Walnuts plant-protein drink (养元饮品)"),
            ("002311.SZ", "Haid Group — animal feed / aquaculture (海大集团)"),
        ],
    },
    # ────────────────────────────── 医药健康 · Healthcare ──────────────────────────────
    "cn_pharma_cxo": {
        "name": "Innovative Pharma & CXO", "name_zh": "创新药与CXO",
        "category": "Healthcare", "category_zh": "医药健康",
        "etf_proxy": "159992.SZ", "etf_proxy_note": "创新药ETF",
        "thesis": "Innovative pharma and CRO/CDMO names tied to licensing, funding and overseas demand.",
        "thesis_zh": "创新药和 CRO/CDMO 公司，受授权交易、融资和海外需求影响。",
        "members": [
            ("603259.SS", "WuXi AppTec — the CXO bellwether (药明康德)"),
            ("600276.SS", "Hengrui — the innovative-drug leader (恒瑞医药)"),
            ("688235.SS", "BeiGene — global oncology biotech (百济神州)"),
            ("300759.SZ", "Pharmaron — pre-clinical CRO (康龙化成)"),
            ("002821.SZ", "Asymchem — small-molecule CDMO (凯莱英)"),
            ("688506.SS", "Baili Tianheng — ADC out-licensing story (百利天恒)"),
            ("688331.SS", "RemeGen — ADC / autoimmune biotech (荣昌生物)"),
            ("002422.SZ", "Kelun — drugs + ADC pipeline (科伦药业)"),
            ("300347.SZ", "Tigermed — clinical CRO (泰格医药)"),
            ("688428.SS", "InnoCare — innovative-oncology biotech (诺诚健华)"),
            ("688180.SS", "Junshi Biosciences — PD-1 / antibody biotech (君实生物)"),
            ("688578.SS", "Allist — EGFR lung-cancer drugs (艾力斯)"),
            ("600196.SS", "Fosun Pharma — pharma + CXO + innovation (复星医药)"),
            ("603087.SS", "Gan & Lee — domestic insulin franchise (甘李药业)"),
        ],
    },
    "cn_med_devices": {
        "name": "Medical Devices & TCM", "name_zh": "医疗器械与中药",
        "category": "Healthcare", "category_zh": "医药健康",
        "etf_proxy": "512170.SS", "etf_proxy_note": "医疗ETF",
        "thesis": "Medical devices, services and TCM brands tied to domestic substitution and defensive health demand.",
        "thesis_zh": "医疗器械、服务和中药品牌，受国产替代和防御性医疗需求影响。",
        "members": [
            ("300760.SZ", "Mindray — the medical-device leader (迈瑞医疗)"),
            ("688271.SS", "United Imaging — high-end imaging systems (联影医疗)"),
            ("300015.SZ", "Aier Eye — ophthalmology hospital chain (爱尔眼科)"),
            ("000538.SZ", "Yunnan Baiyao — branded TCM franchise (云南白药)"),
            ("600436.SS", "Pientzehuang — ultra-premium TCM (片仔癀)"),
            ("000999.SZ", "CR Sanjiu — OTC / TCM brands (华润三九)"),
            ("600085.SS", "Tongrentang — heritage TCM brand (同仁堂)"),
            ("000963.SZ", "Huadong Medicine — pharma + aesthetics (华东医药)"),
            ("688617.SS", "APT Medical — electrophysiology devices (惠泰医疗)"),
            ("300832.SZ", "New Industries — chemiluminescence IVD (新产业)"),
            ("688301.SS", "iRay — X-ray flat-panel detectors (奕瑞科技)"),
            ("300896.SZ", "Imeik — medical-aesthetics filler leader (爱美客)"),
            ("000423.SZ", "Dong-E-E-Jiao — branded ejiao TCM (东阿阿胶)"),
            ("600332.SS", "Baiyunshan — pharma + TCM brands (白云山)"),
        ],
    },
    # ──────────────────────── 金融与价值 · Financials & Value ────────────────────────
    "cn_banks": {
        "name": "Banks", "name_zh": "银行",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": "512800.SS", "etf_proxy_note": "银行ETF",
        "thesis": "Major banks and regional lenders. Core high-dividend read on credit, margins and property risk.",
        "thesis_zh": "大型银行和区域银行。高股息核心板块，反映信贷、息差和地产风险。",
        "members": [
            ("601398.SS", "ICBC — the largest state bank (工商银行)"),
            ("601939.SS", "China Construction Bank (建设银行)"),
            ("601288.SS", "Agricultural Bank of China (农业银行)"),
            ("601988.SS", "Bank of China (中国银行)"),
            ("600036.SS", "China Merchants Bank — premier retail bank (招商银行)"),
            ("601166.SS", "Industrial Bank (兴业银行)"),
            ("600000.SS", "SPD Bank (浦发银行)"),
            ("601328.SS", "Bank of Communications (交通银行)"),
            ("601658.SS", "Postal Savings Bank — retail franchise (邮储银行)"),
            ("000001.SZ", "Ping An Bank — retail growth (平安银行)"),
            ("601998.SS", "CITIC Bank — joint-stock lender (中信银行)"),
            ("600016.SS", "Minsheng Bank — joint-stock lender (民生银行)"),
            ("601818.SS", "Everbright Bank — joint-stock lender (光大银行)"),
            ("002142.SZ", "Bank of Ningbo — top-tier city bank (宁波银行)"),
            ("600919.SS", "Bank of Jiangsu — leading city bank (江苏银行)"),
            ("601169.SS", "Bank of Beijing — largest city bank (北京银行)"),
            ("601009.SS", "Bank of Nanjing — city bank (南京银行)"),
            ("601229.SS", "Bank of Shanghai — city bank (上海银行)"),
        ],
    },
    "cn_brokers": {
        "name": "Brokers & Securities", "name_zh": "券商",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": "512880.SS", "etf_proxy_note": "证券ETF",
        "thesis": "Brokerages and trading platforms tied to turnover, margin balances and capital-market activity.",
        "thesis_zh": "券商和交易平台，受成交额、两融余额和资本市场活跃度影响。",
        "members": [
            ("600030.SS", "CITIC Securities — the #1 broker (中信证券)"),
            ("300059.SZ", "East Money — retail fintech-broker (东方财富)"),
            ("601688.SS", "Huatai Securities (华泰证券)"),
            ("601211.SS", "Guotai Junan — post-Haitong merger (国泰海通)"),
            ("600999.SS", "China Merchants Securities (招商证券)"),
            ("000776.SZ", "GF Securities (广发证券)"),
            ("601066.SS", "CSC Financial (中信建投)"),
            ("601995.SS", "CICC — top investment bank (中金公司)"),
            ("600958.SS", "Orient Securities (东方证券)"),
            ("000166.SZ", "Shenwan Hongyuan (申万宏源)"),
            ("601881.SS", "China Galaxy Securities (中国银河)"),
            ("002736.SZ", "Guosen Securities (国信证券)"),
            ("000783.SZ", "Changjiang Securities (长江证券)"),
            ("601788.SS", "Everbright Securities (光大证券)"),
            ("601377.SS", "Industrial Securities (兴业证券)"),
        ],
    },
    "cn_insurers": {
        "name": "Insurers", "name_zh": "保险",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Life and P&C insurers tied to equity markets, yields and new-business value.",
        "thesis_zh": "寿险和财险公司，受股市、利率和新业务价值影响。",
        "members": [
            ("601318.SS", "Ping An — the integrated insurance leader (中国平安)"),
            ("601628.SS", "China Life — largest life insurer (中国人寿)"),
            ("601601.SS", "China Pacific Insurance (中国太保)"),
            ("601319.SS", "PICC — P&C leader (中国人保)"),
            ("601336.SS", "New China Life (新华保险)"),
        ],
    },
    "cn_soe_value": {
        "name": "SOE Blue Chips (中特估)", "name_zh": "中特估·央企",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Central SOE value basket: oil, telecom, infrastructure and utilities with high dividends.",
        "thesis_zh": "央企价值篮子：石油、电信、基建和公用事业，高股息特征。",
        "members": [
            ("601857.SS", "PetroChina — oil & gas major (中国石油)"),
            ("600028.SS", "Sinopec — refining / chemicals major (中国石化)"),
            ("600938.SS", "CNOOC — offshore E&P, low-cost barrels (中国海油)"),
            ("600941.SS", "China Mobile — carrier + dividend anchor (中国移动)"),
            ("601728.SS", "China Telecom (中国电信)"),
            ("600050.SS", "China Unicom (中国联通)"),
            ("601668.SS", "China State Construction (中国建筑)"),
            ("601390.SS", "China Railway Group (中国中铁)"),
            ("601186.SS", "China Railway Construction (中国铁建)"),
            ("600900.SS", "Yangtze Power — hydro / dividend (长江电力)"),
            ("601800.SS", "China Communications Construction — infra major (中国交建)"),
            ("601618.SS", "MCC — metallurgical / infra SOE (中国中冶)"),
            ("601669.SS", "PowerChina — power-grid / infra SOE (中国电建)"),
            ("601766.SS", "CRRC — rolling-stock champion (中国中车)"),
            ("601117.SS", "China National Chemical Eng. (中国化学)"),
            ("601919.SS", "COSCO Shipping Holdings — container shipping SOE (中远海控)"),
        ],
    },
    # ─────────────────────── 周期与资源 · Cyclicals & Resources ───────────────────────
    "cn_gold": {
        "name": "Gold Miners", "name_zh": "黄金",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Gold miners levered to bullion, real rates and central-bank demand.",
        "thesis_zh": "黄金矿商，受金价、实际利率和央行需求影响。",
        "members": [
            ("601899.SS", "Zijin Mining — gold + copper giant (紫金矿业)"),
            ("600547.SS", "Shandong Gold — pure-play producer (山东黄金)"),
            ("600489.SS", "Zhongjin Gold — SOE producer (中金黄金)"),
            ("600988.SS", "Chifeng Gold — fast-growing miner (赤峰黄金)"),
            ("002155.SZ", "Hunan Gold — gold + antimony/tungsten (湖南黄金)"),
            ("000975.SZ", "Shanjin International — gold producer (山金国际)"),
        ],
    },
    "cn_metals": {
        "name": "Industrial Metals", "name_zh": "有色金属",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "512400.SS", "etf_proxy_note": "有色金属ETF",
        "thesis": "Copper, aluminium and industrial metals producers tied to global growth and green capex.",
        "thesis_zh": "铜、铝和工业金属生产商，受全球增长和绿色资本开支影响。",
        "members": [
            ("603993.SS", "CMOC — copper / cobalt / moly (洛阳钼业)"),
            ("600362.SS", "Jiangxi Copper — copper leader (江西铜业)"),
            ("601600.SS", "Chalco — aluminium major (中国铝业)"),
            ("000807.SZ", "Yunnan Aluminium — green-power smelting (云铝股份)"),
            ("000630.SZ", "Tongling Nonferrous — copper (铜陵有色)"),
            ("002379.SZ", "Shandong Hongqiao — top aluminium (宏桥/魏桥)"),
            ("002532.SZ", "Tianshan Aluminium — integrated smelter (天山铝业)"),
            ("601899.SS", "Zijin Mining — copper / gold giant (紫金矿业)"),
            ("000878.SZ", "Yunnan Copper (云南铜业)"),
            ("601168.SS", "Western Mining — copper / zinc / lead (西部矿业)"),
            ("601958.SS", "Jinduicheng Molybdenum — moly (金钼股份)"),
            ("000960.SZ", "Yunnan Tin — global tin leader (锡业股份)"),
            ("000060.SZ", "Zhongjin Lingnan — lead / zinc (中金岭南)"),
        ],
    },
    "cn_rare_earth": {
        "name": "Rare Earth & Magnets", "name_zh": "稀土永磁",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "512400.SS", "etf_proxy_note": "loose — broad nonferrous ETF",
        "thesis": "Rare-earth and magnet makers tied to EV motors, wind, robotics and export controls.",
        "thesis_zh": "稀土和磁材公司，受电机、风电、机器人和出口管制影响。",
        "members": [
            ("600111.SS", "Northern Rare Earth — the resource giant (北方稀土)"),
            ("000831.SZ", "China Rare Earth — SOE consolidator (中国稀土)"),
            ("300748.SZ", "JL MAG — NdFeB magnets leader (金力永磁)"),
            ("600392.SS", "Shenghe Resources — rare-earth trade/processing (盛和资源)"),
            ("600549.SS", "Xiamen Tungsten — tungsten + rare earth (厦门钨业)"),
            ("000657.SZ", "China Tungsten & Hightech — tungsten (中钨高新)"),
            ("002056.SZ", "DMEGC — NdFeB + ferrite magnets (横店东磁)"),
            ("002378.SZ", "Zhangyuan Tungsten — tungsten (章源钨业)"),
            ("600259.SS", "Rising Nonferrous — rare-earth processing (中稀有色)"),
        ],
    },
    "cn_coal": {
        "name": "Coal", "name_zh": "煤炭",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "515220.SS", "etf_proxy_note": "煤炭ETF",
        "thesis": "Coal producers with high payout and power-demand exposure.",
        "thesis_zh": "煤炭生产商，高派息并受电力需求影响。",
        "members": [
            ("601088.SS", "China Shenhua — integrated coal/power dividend anchor (中国神华)"),
            ("601225.SS", "Shaanxi Coal — low-cost thermal coal (陕西煤业)"),
            ("601898.SS", "China Coal Energy (中煤能源)"),
            ("600188.SS", "Yankuang Energy — coal + chemicals (兖矿能源)"),
            ("601699.SS", "Lu'an Environmental — coking/thermal (潞安环能)"),
            ("000983.SZ", "Shanxi Coking Coal (山西焦煤)"),
            ("600985.SS", "Huaibei Mining — coking coal (淮北矿业)"),
            ("601001.SS", "Jinkong Coal — Shanxi thermal coal (晋控煤业)"),
            ("600348.SS", "Huayang — anthracite / new-energy materials (华阳股份)"),
            ("600925.SS", "Jiangsu Xukuang Energy — coal + power (苏能股份)"),
        ],
    },
}

# ── Post-seed removals (COPY SYNC with the live membership.json) ────────────────────────
# The nightly membership↔cache reconciler (scripts/reconcile_membership.py, end-of-collect
# gate) prunes members whose ticker drops off the china_search close cache, appending a
# dated changelog entry to the LIVE file. Those removals are re-encoded here so a wholesale
# regen reproduces the live file instead of resurrecting the member or failing the cache
# check. The member's tuple STAYS in BASKETS above (it feeds the historical member count in
# the create note); the (basket_id, ticker) key here excludes it from the emitted members
# and appends the exact changelog row. Notes are verbatim from the live file — don't reword.
# 300073.SZ Easpring (当升科技): still listed on ChiNext, but fell below the china_search
# top-N-mktcap universe cutoff (pre-append-only collector erased its history column; not in
# dropped.parquet, so no frozen ~2y retention window applies). Genuine universe trim.
REMOVED: dict[tuple[str, str], dict] = {
    ("cn_battery", "300073.SZ"): {
        "date": "2026-07-01",
        "note": ("300073.SZ: removed — 当升科技 dropped out of the china_search universe/close "
                 "cache, so its price history is no longer computable (cache-validation "
                 "contract: every member must be a live close-cache column). "
                 "16 members remain."),
    },
    # 600562.SS / 603345.SS have since RE-ENTERED the live cache (top-N churn) — the seeder
    # warns about them at regen; re-adding is a curation decision, not an auto-revert.
    ("cn_defense", "600562.SS"): {
        "date": "2026-07-01",
        "note": ("600562.SS: removed — 国睿科技 dropped out of the china_search universe/close "
                 "cache, so its price history is no longer computable (cache-validation "
                 "contract: every member must be a live close-cache column). "
                 "13 members remain."),
    },
    ("cn_food_bev", "603345.SS"): {
        "date": "2026-07-01",
        "note": ("603345.SS: removed — 安井食品 dropped out of the china_search universe/close "
                 "cache, so its price history is no longer computable (cache-validation "
                 "contract: every member must be a live close-cache column). "
                 "10 members remain."),
    },
}

CONSTRUCTION = "Equal-weight baskets, rebalanced monthly, measured against CSI 300."
HISTORY_NOTE = ("Available history comes from the china_search cache. Pre-launch series use "
                "the basket's starting membership.")
NOTE = ("Curated A-share theme baskets for monitoring rotation. Descriptive only, not a "
        "buy list.")


def main() -> int:
    members_p = config.data_dir() / "china_search" / "members.parquet"
    closes_p = config.data_dir() / "china_search" / "closes.parquet"
    out_dir = config.data_dir() / "baskets_china"
    meta = pd.read_parquet(members_p)
    cols = set(pd.read_parquet(closes_p, columns=None).columns)

    # Names already in the LIVE membership file — the fallback when members.parquet is
    # degraded for a ticker: top-N dropouts lose their meta row (name would collapse to the
    # raw ticker), and on ex-div/ex-rights days Sina ships truncated tagged names (XD/XR/DR
    # + 4 chars, e.g. 中国银行 → XD中国银) that must never overwrite a good name.
    live_names: dict[tuple[str, str], str] = {}
    live_p = out_dir / "membership.json"
    if live_p.exists():
        try:
            live_doc = json.loads(live_p.read_text())
            live_names = {(bid, m["ticker"]): m["name_zh"]
                          for bid, b in live_doc.get("baskets", {}).items()
                          for m in b.get("members", []) if m.get("name_zh")}
        except Exception as e:  # noqa: BLE001 — degraded live file just loses the fallback
            log.warning("live membership.json unreadable (%s) — no name fallback", e)

    def zh_name(bid: str, t: str) -> str:
        v = meta.loc[t, "name_zh"] if t in meta.index else None
        s = str(v).replace(" ", "") if v is not None and pd.notna(v) else ""
        if s and not s.startswith(("XD", "XR", "DR")):
            return s
        return live_names.get((bid, t)) or (s or t)

    out_baskets: dict[str, dict] = {}
    missing_all: list[str] = []
    for bid, b in BASKETS.items():
        members, removals = [], []
        for ticker, rationale in b["members"]:
            rm = REMOVED.get((bid, ticker))
            if rm is not None:
                if ticker in cols:
                    log.warning("removed member %s:%s is back on the china_search cache — "
                                "consider re-adding it with a dated changelog entry", bid, ticker)
                removals.append(rm)
                continue
            if ticker not in cols:
                missing_all.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name_zh": zh_name(bid, ticker), "rationale": rationale})
        n_seeded = len(members) + len(removals)   # count at seed date, before later removals
        cl = [{"date": SEED, "action": "create",
               "note": f"Seeded {b['name']} — {n_seeded} equal-weight A-share members."}]
        cl += [{"date": rm["date"], "action": "remove", "note": rm["note"]} for rm in removals]
        out_baskets[bid] = {
            "name": b["name"], "name_zh": b["name_zh"],
            "category": b["category"], "category_zh": b["category_zh"],
            "etf_proxy": b["etf_proxy"], "etf_proxy_note": b["etf_proxy_note"],
            "created": SEED, "weighting": "equal",
            "thesis": b["thesis"], "thesis_zh": b["thesis_zh"],
            "members": members,
            "changelog": cl,
        }

    if missing_all:
        log.error("TICKERS NOT IN china_search cache (fix before shipping): %s", ", ".join(missing_all))
        return 1

    payload = {
        "version": SEED, "seed_date": SEED, "curated": SEED,
        "benchmark": "510300.SS", "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300",
        "construction": CONSTRUCTION, "history_note": HISTORY_NOTE, "note": NOTE,
        "baskets": out_baskets,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / "membership.json"
    out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n_members = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d baskets, %d members, all tickers validated against china_search",
             out_p, len(out_baskets), n_members)
    return 0


if __name__ == "__main__":
    sys.exit(main())
