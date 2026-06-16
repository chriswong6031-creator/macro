"""Seed data/baskets_china/membership.json — curated A-share thematic baskets.

The China analogue of data/baskets/membership.json. Defines recognizable A-share
themes (白酒 baijiu, 半导体 semis, AI 算力 compute, 锂电 battery, 中特估 SOE value …)
and their equal-weight member tickers, then materialises the same membership schema
engine.baskets_china.compute_china_baskets() consumes.

Authoring contract: here we hand-curate only (ticker, English rationale) per member
plus the bilingual theme name / thesis / ETF proxy. The member's Chinese name is filled
from data/china_search/members.parquet, and EVERY ticker is validated against the
china_search close cache (fail loud if any is absent) so the page never silently drops a
member. Re-runnable: `python -m scripts.seed_china_baskets`.

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
        "thesis": "The chip-localization (国产替代) complex: foundries, equipment, design IP and memory racing to build a domestic stack as export controls tighten. The purest read on China's self-sufficiency drive — high-beta, policy- and cycle-sensitive.",
        "thesis_zh": "国产替代主线：晶圆代工、设备、设计与存储在出口管制下加速构建本土产业链。最纯粹的自主可控读数 — 高弹性，受政策与周期驱动。",
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
        ],
    },
    "cn_ai_compute": {
        "name": "AI Compute & Optics", "name_zh": "AI算力与光模块",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "The AI capex hardware leg: 800G optical modules, AI servers, switch silicon and domestic accelerators that the data-centre build-out is denominated in. China's most explosive 2024-25 momentum theme and its tightest link to the global AI cycle.",
        "thesis_zh": "AI 资本开支硬件腿：800G 光模块、AI 服务器、交换芯片与国产算力 — 数据中心建设的承载者。2024-25 最具爆发力的动量主题，与全球 AI 周期联系最紧。",
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
        ],
    },
    "cn_consumer_elec": {
        "name": "Consumer Electronics", "name_zh": "消费电子",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "The Apple/Android hardware supply chain (果链): precision assembly, acoustics, glass, display and PCB. Levered to the smartphone cycle, AI-phone refresh and any handset-AI hardware upgrade.",
        "thesis_zh": "苹果/安卓硬件供应链（果链）：精密组装、声学、玻璃、面板与 PCB。受智能手机周期、AI 手机换机与端侧 AI 硬件升级驱动。",
        "members": [
            ("002475.SZ", "Luxshare — top precision-assembly / connectors (立讯精密)"),
            ("002241.SZ", "GoerTek — acoustics + AR/VR hardware (歌尔股份)"),
            ("300433.SZ", "Lens Technology — cover glass / casings (蓝思科技)"),
            ("000725.SZ", "BOE — the dominant display panel maker (京东方)"),
            ("002384.SZ", "Dongshan Precision — FPC / PCB (东山精密)"),
            ("002938.SZ", "Avary Holding — flex-PCB leader (鹏鼎控股)"),
            ("002600.SZ", "Lingyi iTech — functional parts / assembly (领益智造)"),
            ("002273.SZ", "Crystal-Optech — optical filters / imaging (水晶光电)"),
        ],
    },
    "cn_software": {
        "name": "Software & AI Apps", "name_zh": "软件与AI应用",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Domestic software, fintech-data and the AIGC application layer (信创 + AI 应用): office suites, speech/LLM, financial terminals and security. Levered to IT-localization mandates and the monetisation of generative AI in China.",
        "thesis_zh": "国产软件、金融数据与 AIGC 应用层（信创+AI应用）：办公套件、语音/大模型、金融终端与安全。受信创政策与生成式 AI 商业化驱动。",
        "members": [
            ("688111.SS", "Kingsoft Office — WPS suite + AI copilot (金山办公)"),
            ("002230.SZ", "iFlytek — speech & LLM platform (科大讯飞)"),
            ("600570.SS", "Hundsun — financial-institution software (恒生电子)"),
            ("300454.SZ", "Sangfor — security / cloud infrastructure (深信服)"),
            ("600845.SS", "Baosight — industrial software (宝信软件)"),
            ("300033.SZ", "Hithink RoyalFlush — retail fintech data (同花顺)"),
            ("300418.SZ", "Kunlun Tech — AIGC / overseas internet (昆仑万维)"),
            ("600588.SS", "Yonyou — enterprise ERP / cloud (用友网络)"),
        ],
    },
    # ─────────────────────── 新能源与汽车 · New Energy & Autos ───────────────────────
    "cn_battery": {
        "name": "Battery & Lithium", "name_zh": "锂电池",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515030.SS", "etf_proxy_note": "新能源车ETF — battery-heavy",
        "thesis": "The lithium-battery value chain — cells, lithium resource, separators, electrolyte and anode/cathode. China's dominant export-competitive complex; whipsawed by the lithium price cycle and global EV demand.",
        "thesis_zh": "锂电池价值链 — 电芯、锂资源、隔膜、电解液与正负极。中国最具出口竞争力的产业集群；受锂价周期与全球电动车需求剧烈牵动。",
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
        ],
    },
    "cn_solar": {
        "name": "Solar / Photovoltaics", "name_zh": "光伏",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515790.SS", "etf_proxy_note": "光伏ETF",
        "thesis": "The solar manufacturing chain — silicon, wafers, cells, modules, inverters and film. A textbook over-capacity / price-war cyclical: huge global volume growth wrestling with brutal margin compression.",
        "thesis_zh": "光伏制造链 — 硅料、硅片、电池、组件、逆变器与胶膜。典型的产能过剩/价格战周期：全球装机高增长与残酷的盈利压缩并存。",
        "members": [
            ("601012.SS", "LONGi — wafer + module leader (隆基绿能)"),
            ("600438.SS", "Tongwei — polysilicon + cells (通威股份)"),
            ("300274.SZ", "Sungrow — #1 inverter / storage (阳光电源)"),
            ("002129.SZ", "TCL Zhonghuan — silicon wafers (TCL中环)"),
            ("688223.SS", "Jinko Solar — top global module shipper (晶科能源)"),
            ("688303.SS", "Daqo — polysilicon pure-play (大全能源)"),
            ("603806.SS", "Foster — EVA encapsulant film leader (福斯特)"),
            ("688472.SS", "CSI Solar — modules + storage (阿特斯)"),
        ],
    },
    "cn_autos": {
        "name": "Autos & NEV Makers", "name_zh": "汽车整车",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515250.SS", "etf_proxy_note": "智能汽车ETF",
        "thesis": "Whole-vehicle makers and key suppliers riding the EV/intelligent-driving transition and the export push — legacy OEMs reinventing, new-energy champions scaling, and the parts names (glass, thermal, smart-cockpit) levered to content-per-car.",
        "thesis_zh": "整车与核心零部件，受电动化/智能化转型与出口浪潮驱动 — 传统车企转身、新能源龙头放量，零部件（玻璃、热管理、智能座舱）受单车价值量提升带动。",
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
        ],
    },
    # ─────────────────────── 高端制造 · Advanced Manufacturing ───────────────────────
    "cn_defense": {
        "name": "Defense & Aerospace", "name_zh": "军工航天",
        "category": "Advanced Manufacturing", "category_zh": "高端制造",
        "etf_proxy": "512660.SS", "etf_proxy_note": "军工ETF",
        "thesis": "The military-industrial complex — fighters, aero-engines, shipbuilding, milconnectors, infrared and satellites. A policy/order-book theme driven by the defense budget and modernization, largely decoupled from the consumer cycle.",
        "thesis_zh": "军工产业链 — 战机、航发、船舶、军工连接器、红外与卫星。受国防预算与现代化订单驱动的政策主题，与消费周期基本脱钩。",
        "members": [
            ("600760.SS", "AVIC Shenyang — fighter-jet prime (中航沈飞)"),
            ("302132.SZ", "AVIC Chengdu — J-series fighters (中航成飞)"),
            ("600893.SS", "AECC Aviation Power — aero-engines (航发动力)"),
            ("000768.SZ", "AVIC Xi'an — bombers / transports (中航西飞)"),
            ("002179.SZ", "Jonhon — defense connectors (中航光电)"),
            ("600150.SS", "CSSC — shipbuilding champion (中国船舶)"),
            ("600118.SS", "China Spacesat — satellites (中国卫星)"),
            ("002414.SZ", "Guide Infrared — thermal imaging (高德红外)"),
        ],
    },
    "cn_robotics": {
        "name": "Robotics & Automation", "name_zh": "机器人与自动化",
        "category": "Advanced Manufacturing", "category_zh": "高端制造",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Industrial automation and the humanoid-robot supply chain — servo drives, harmonic reducers, controllers and thermal/actuator parts. A high-beta 2024-25 thematic on the humanoid build-out and factory automation.",
        "thesis_zh": "工业自动化与人形机器人供应链 — 伺服、谐波减速器、控制器与热管理/执行部件。受人形机器人放量与工厂自动化驱动的高弹性 2024-25 主题。",
        "members": [
            ("300124.SZ", "Inovance — servo / motion-control leader (汇川技术)"),
            ("688017.SS", "Leader Drive — harmonic reducers (绿的谐波)"),
            ("002747.SZ", "Estun — industrial robots (埃斯顿)"),
            ("300024.SZ", "Siasun — robotics pioneer (机器人/新松)"),
            ("002472.SZ", "Shuanghuan — precision gears / RV reducers (双环传动)"),
            ("002050.SZ", "Sanhua — thermal mgmt + humanoid actuators (三花智控)"),
        ],
    },
    # ────────────────────────── 核心消费 · Consumer & Brands ──────────────────────────
    "cn_baijiu": {
        "name": "Baijiu / Liquor", "name_zh": "白酒",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": "512690.SS", "etf_proxy_note": "酒ETF",
        "thesis": "The baijiu complex — the bellwether of Chinese premium consumption and the market's quintessential quality-franchise basket. Pricing power and mix versus the property-driven consumption-confidence cycle.",
        "thesis_zh": "白酒板块 — 中国高端消费的风向标，也是市场最具代表性的优质消费特许经营篮子。提价与产品结构对决地产驱动的消费信心周期。",
        "members": [
            ("600519.SS", "Kweichow Moutai — the ultra-premium anchor (贵州茅台)"),
            ("000858.SZ", "Wuliangye — the #2 premium brand (五粮液)"),
            ("000568.SZ", "Luzhou Laojiao — premium + mid-range (泸州老窖)"),
            ("600809.SS", "Shanxi Fenjiu — fast-growing fragrance baijiu (山西汾酒)"),
            ("002304.SZ", "Yanghe — east-China leader (洋河股份)"),
            ("000596.SZ", "Gujing Gong — regional premium (古井贡酒)"),
        ],
    },
    "cn_appliances": {
        "name": "Home Appliances", "name_zh": "家电",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "White-goods and appliance champions — global-scale, high-ROE, dividend-paying franchises levered to trade-in stimulus (以旧换新), export share gains and the property after-cycle.",
        "thesis_zh": "白电与家电龙头 — 全球规模、高 ROE、分红型特许经营，受以旧换新刺激、出口份额提升与地产后周期驱动。",
        "members": [
            ("000333.SZ", "Midea — diversified appliance + robotics (美的集团)"),
            ("000651.SZ", "Gree — air-conditioning leader (格力电器)"),
            ("600690.SS", "Haier Smart Home — global premium brands (海尔智家)"),
            ("000921.SZ", "Hisense Home Appliances — AC + white goods (海信家电)"),
            ("600060.SS", "Hisense Visual — TV / display (海信视像)"),
            ("002032.SZ", "Supor — small kitchen appliances (苏泊尔)"),
        ],
    },
    "cn_food_bev": {
        "name": "Food & Beverage", "name_zh": "食品饮料",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": "159928.SZ", "etf_proxy_note": "消费ETF — staples",
        "thesis": "Staple food and non-alcoholic beverage leaders — dairy, condiments, energy drinks, cooking oil and meat. Defensive consumption with brand power; a barometer of mass-market demand and input-cost cycles.",
        "thesis_zh": "必选食品与软饮龙头 — 乳制品、调味品、功能饮料、食用油与肉制品。具品牌力的防御性消费，是大众需求与成本周期的晴雨表。",
        "members": [
            ("600887.SS", "Yili — the dairy leader (伊利股份)"),
            ("603288.SS", "Haitian — soy sauce / condiments king (海天味业)"),
            ("605499.SS", "Eastroc Beverage — energy-drink growth (东鹏饮料)"),
            ("300999.SZ", "Arawana — cooking oil / staples (金龙鱼)"),
            ("000895.SZ", "Shuanghui — meat processing leader (双汇发展)"),
            ("600600.SS", "Tsingtao Brewery — premium beer (青岛啤酒)"),
        ],
    },
    # ────────────────────────────── 医药健康 · Healthcare ──────────────────────────────
    "cn_pharma_cxo": {
        "name": "Innovative Pharma & CXO", "name_zh": "创新药与CXO",
        "category": "Healthcare", "category_zh": "医药健康",
        "etf_proxy": "159992.SZ", "etf_proxy_note": "创新药ETF",
        "thesis": "Innovative-drug developers and the CXO outsourcing chain (CRO/CDMO). The R&D-and-globalization growth engine of China healthcare — levered to out-licensing deals, biotech funding and overseas demand.",
        "thesis_zh": "创新药企与 CXO 外包链（CRO/CDMO）。中国医药的研发与出海成长引擎 — 受对外授权（BD）、生物科技融资与海外需求驱动。",
        "members": [
            ("603259.SS", "WuXi AppTec — the CXO bellwether (药明康德)"),
            ("600276.SS", "Hengrui — the innovative-drug leader (恒瑞医药)"),
            ("688235.SS", "BeiGene — global oncology biotech (百济神州)"),
            ("300759.SZ", "Pharmaron — pre-clinical CRO (康龙化成)"),
            ("002821.SZ", "Asymchem — small-molecule CDMO (凯莱英)"),
            ("688506.SS", "Baili Tianheng — ADC out-licensing story (百利天恒)"),
            ("688331.SS", "RemeGen — ADC / autoimmune biotech (荣昌生物)"),
            ("002422.SZ", "Kelun — drugs + ADC pipeline (科伦药业)"),
        ],
    },
    "cn_med_devices": {
        "name": "Medical Devices & TCM", "name_zh": "医疗器械与中药",
        "category": "Healthcare", "category_zh": "医药健康",
        "etf_proxy": "512170.SS", "etf_proxy_note": "医疗ETF",
        "thesis": "Medical-equipment makers, healthcare services and branded traditional-Chinese-medicine (中药) franchises — domestic-substitution device leaders plus defensive, pricing-power consumer-health brands.",
        "thesis_zh": "医疗设备、医疗服务与品牌中药特许经营 — 国产替代的器械龙头，叠加具提价能力的防御型消费医疗品牌。",
        "members": [
            ("300760.SZ", "Mindray — the medical-device leader (迈瑞医疗)"),
            ("688271.SS", "United Imaging — high-end imaging systems (联影医疗)"),
            ("300015.SZ", "Aier Eye — ophthalmology hospital chain (爱尔眼科)"),
            ("000538.SZ", "Yunnan Baiyao — branded TCM franchise (云南白药)"),
            ("600436.SS", "Pientzehuang — ultra-premium TCM (片仔癀)"),
            ("000999.SZ", "CR Sanjiu — OTC / TCM brands (华润三九)"),
            ("600085.SS", "Tongrentang — heritage TCM brand (同仁堂)"),
            ("000963.SZ", "Huadong Medicine — pharma + aesthetics (华东医药)"),
        ],
    },
    # ──────────────────────── 金融与价值 · Financials & Value ────────────────────────
    "cn_banks": {
        "name": "Banks", "name_zh": "银行",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": "512800.SS", "etf_proxy_note": "银行ETF",
        "thesis": "The banking complex — the big-four state lenders, the joint-stock leaders and the high-growth city/rural banks. The core of the high-dividend (高股息) trade and a direct read on credit, net-interest-margin and property risk.",
        "thesis_zh": "银行板块 — 国有大行、股份行龙头与高成长城农商行。高股息交易的核心，也是信用、净息差与地产风险的直接读数。",
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
        ],
    },
    "cn_brokers": {
        "name": "Brokers & Securities", "name_zh": "券商",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": "512880.SS", "etf_proxy_note": "证券ETF",
        "thesis": "Securities firms and the fintech-trading platforms — the high-beta vanguard of any A-share bull market. Levered to turnover, margin balances, IPO/M&A activity and consolidation among the majors.",
        "thesis_zh": "证券公司与金融科技交易平台 — A 股牛市的高弹性先锋。受成交额、两融余额、IPO/并购活动与头部券商整合驱动。",
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
        ],
    },
    "cn_insurers": {
        "name": "Insurers", "name_zh": "保险",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The big listed insurers — life and P&C franchises whose earnings and book value swing on the equity market, long-bond yields and new-business value. A leveraged play on a domestic risk-on turn.",
        "thesis_zh": "上市大型险企 — 寿险与财险特许经营，利润与净资产随权益市场、长债收益率与新业务价值波动。对国内风险偏好回升的杠杆化表达。",
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
        "thesis": "The state-owned-enterprise re-rating theme (中国特色估值体系) — the three oil majors, the telecom carriers and the big infrastructure/utility SOEs. A policy-driven, high-dividend value trade on raising returns and valuations of central SOEs.",
        "thesis_zh": "央企估值重塑主题（中国特色估值体系）— 三桶油、电信运营商与大型基建/公用事业央企。受提升央企回报与估值政策驱动的高股息价值交易。",
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
        ],
    },
    # ─────────────────────── 周期与资源 · Cyclicals & Resources ───────────────────────
    "cn_gold": {
        "name": "Gold Miners", "name_zh": "黄金",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The gold-mining complex — producers levered to the bullion price, central-bank buying and the real-rate / de-dollarization narrative. A high-beta way to express the gold cycle from A-shares.",
        "thesis_zh": "黄金采矿板块 — 受金价、央行购金与实际利率/去美元化叙事驱动的生产商。从 A 股表达黄金周期的高弹性方式。",
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
        "thesis": "Base and industrial metals — copper, aluminium and molybdenum producers levered to the global growth cycle, the green-capex demand pull and supply discipline. The China read on the commodity super-theme.",
        "thesis_zh": "基本金属与工业金属 — 铜、铝、钼生产商，受全球增长周期、绿色资本开支需求与供给约束驱动。表达大宗超级主题的中国读数。",
        "members": [
            ("603993.SS", "CMOC — copper / cobalt / moly (洛阳钼业)"),
            ("600362.SS", "Jiangxi Copper — copper leader (江西铜业)"),
            ("601600.SS", "Chalco — aluminium major (中国铝业)"),
            ("000807.SZ", "Yunnan Aluminium — green-power smelting (云铝股份)"),
            ("000630.SZ", "Tongling Nonferrous — copper (铜陵有色)"),
            ("002379.SZ", "Shandong Hongqiao — top aluminium (宏桥/魏桥)"),
            ("002532.SZ", "Tianshan Aluminium — integrated smelter (天山铝业)"),
        ],
    },
    "cn_rare_earth": {
        "name": "Rare Earth & Magnets", "name_zh": "稀土永磁",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "512400.SS", "etf_proxy_note": "loose — broad nonferrous ETF",
        "thesis": "Rare-earth resource and permanent-magnet makers — the upstream of EV motors, wind turbines and robotics, and a strategic export-control chokepoint. A policy-and-price theme on China's near-monopoly in the supply chain.",
        "thesis_zh": "稀土资源与永磁制造 — 电机、风机与机器人的上游，也是战略出口管制的咽喉。受中国近乎垄断供应链的政策与价格驱动的主题。",
        "members": [
            ("600111.SS", "Northern Rare Earth — the resource giant (北方稀土)"),
            ("000831.SZ", "China Rare Earth — SOE consolidator (中国稀土)"),
            ("300748.SZ", "JL MAG — NdFeB magnets leader (金力永磁)"),
            ("600392.SS", "Shenghe Resources — rare-earth trade/processing (盛和资源)"),
            ("600549.SS", "Xiamen Tungsten — tungsten + rare earth (厦门钨业)"),
            ("000657.SZ", "China Tungsten & Hightech — tungsten (中钨高新)"),
        ],
    },
    "cn_coal": {
        "name": "Coal", "name_zh": "煤炭",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "515220.SS", "etf_proxy_note": "煤炭ETF",
        "thesis": "Thermal and coking coal producers — the heart of the high-dividend (红利) trade: heavy free-cash-flow, high payout ratios and pricing tied to power demand and supply policy. Defensive yield with cyclical tail risk.",
        "thesis_zh": "动力煤与焦煤生产商 — 红利交易的核心：充沛自由现金流、高分红比例，价格挂钩电力需求与供给政策。带周期尾部风险的防御性高股息。",
        "members": [
            ("601088.SS", "China Shenhua — integrated coal/power dividend anchor (中国神华)"),
            ("601225.SS", "Shaanxi Coal — low-cost thermal coal (陕西煤业)"),
            ("601898.SS", "China Coal Energy (中煤能源)"),
            ("600188.SS", "Yankuang Energy — coal + chemicals (兖矿能源)"),
            ("601699.SS", "Lu'an Environmental — coking/thermal (潞安环能)"),
            ("000983.SZ", "Shanxi Coking Coal (山西焦煤)"),
        ],
    },
}

CONSTRUCTION = ("Equal-weighted, monthly-rebalanced, buy-and-hold between rebalances; dated "
                "membership changes take effect same-day. Benchmark = CSI 300 (沪深300).")
HISTORY_NOTE = ("Series before a basket's creation date are a backtest of the membership as of "
                "creation; live tracking starts at creation. Universe = the free china_search "
                "top-market-cap A-share cache (~5y).")
NOTE = ("Curated A-share thematic baskets — hindsight-curated and descriptive, not an "
        "out-of-sample backtest and not a buy list.")


def main() -> int:
    members_p = config.data_dir() / "china_search" / "members.parquet"
    closes_p = config.data_dir() / "china_search" / "closes.parquet"
    meta = pd.read_parquet(members_p)
    cols = set(pd.read_parquet(closes_p, columns=None).columns)

    def zh_name(t: str) -> str:
        if t in meta.index:
            v = meta.loc[t, "name_zh"]
            return str(v).replace(" ", "") if pd.notna(v) else t
        return t

    out_baskets: dict[str, dict] = {}
    missing_all: list[str] = []
    for bid, b in BASKETS.items():
        members = []
        for ticker, rationale in b["members"]:
            if ticker not in cols:
                missing_all.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name_zh": zh_name(ticker), "rationale": rationale})
        out_baskets[bid] = {
            "name": b["name"], "name_zh": b["name_zh"],
            "category": b["category"], "category_zh": b["category_zh"],
            "etf_proxy": b["etf_proxy"], "etf_proxy_note": b["etf_proxy_note"],
            "created": SEED, "weighting": "equal",
            "thesis": b["thesis"], "thesis_zh": b["thesis_zh"],
            "members": members,
            "changelog": [{"date": SEED, "action": "create",
                           "note": f"Seeded {b['name']} — {len(members)} equal-weight A-share members."}],
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
    out_dir = config.data_dir() / "baskets_china"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / "membership.json"
    out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n_members = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d baskets, %d members, all tickers validated against china_search",
             out_p, len(out_baskets), n_members)
    return 0


if __name__ == "__main__":
    sys.exit(main())
