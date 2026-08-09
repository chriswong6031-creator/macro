"""Seed data/baskets_china/membership.json — curated A-share thematic baskets.

The China analogue of data/baskets/membership.json. Defines recognizable A-share
themes (白酒 baijiu, 半导体 semis, AI 算力 compute, 锂电 battery, 中特估 SOE value …)
and their equal-weight member tickers, then materialises the same membership schema
engine.baskets_china.compute_china_baskets() consumes.

Authoring contract: here we hand-curate only (ticker, English rationale, Chinese rationale)
per member plus the bilingual theme name / thesis / ETF proxy. Both rationales must carry the
DESCRIPTOR, not just the company name — the members table already shows the name in its own
column, so a bare-name blurb makes the 说明 / Rationale column dead weight. The Chinese name is filled
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
#                          thesis, thesis_zh, members=[(ticker, rationale_en, rationale_zh), ...])
BASKETS: dict[str, dict] = {
    # ───────────────────────── 科技与AI · Technology & AI ─────────────────────────
    "cn_semis": {
        "name": "Semiconductors", "name_zh": "半导体",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "512760.SS", "etf_proxy_note": "半导体ETF — chip-localization basket",
        "thesis": "China chip-localization names across foundry, equipment, design and memory.",
        "thesis_zh": "中国芯片国产化公司，覆盖晶圆代工、设备、设计和存储。",
        "members": [
            ("688981.SS", "SMIC — the flagship foundry; the core of mainland capacity",
             "中芯国际 — 龙头晶圆代工；大陆产能的核心"),
            ("688256.SS", "Cambricon — domestic AI accelerator; the NVDA-alternative bet",
             "寒武纪 — 国产AI加速芯片；替代英伟达的核心押注"),
            ("002371.SZ", "NAURA — leading semiconductor equipment (etch/deposition)",
             "北方华创 — 半导体设备龙头（刻蚀、薄膜沉积）"),
            ("688041.SS", "Hygon — x86 server CPUs / DCU compute",
             "海光信息 — 国产服务器处理器与加速卡算力"),
            ("688347.SS", "Hua Hong — mature-node specialty foundry",
             "华虹公司 — 成熟制程特色工艺代工"),
            ("603986.SS", "GigaDevice — NOR flash + MCU design leader",
             "兆易创新 — 闪存与微控制器设计龙头"),
            ("688012.SS", "AMEC — etch-tool champion (中微公司)",
             "中微公司 — 刻蚀设备冠军"),
            ("688008.SS", "Montage — interface/memory-buffer chips (DDR5 cycle)",
             "澜起科技 — 内存接口与缓冲芯片，受内存换代周期驱动"),
            ("300782.SZ", "Maxscend — RF front-end modules (卓胜微)",
             "卓胜微 — 射频前端模组"),
            ("002049.SZ", "Unigroup Guoxin — FPGA / special-purpose ICs",
             "紫光国微 — 可编程逻辑与特种集成电路"),
            ("688082.SS", "ACM Research Shanghai — cleaning / plating equipment (盛美上海)",
             "盛美上海 — 清洗与电镀设备"),
            ("688072.SS", "Piotech — thin-film deposition (PECVD) equipment (拓荆科技)",
             "拓荆科技 — 薄膜沉积设备"),
            ("688120.SS", "Hwatsing — CMP polishing equipment (华海清科)",
             "华海清科 — 化学机械抛光设备"),
            ("688126.SS", "NSIG — 300mm silicon-wafer leader (沪硅产业)",
             "沪硅产业 — 300毫米大硅片龙头"),
            ("600584.SS", "JCET — #1 OSAT advanced packaging (长电科技)",
             "长电科技 — 封测第一，先进封装"),
            ("002156.SZ", "Tongfu Micro — OSAT packaging, AMD JV (通富微电)",
             "通富微电 — 封装测试，与超威合资"),
            ("600460.SS", "Silan Micro — power-semi IDM (士兰微)",
             "士兰微 — 功率半导体一体化制造"),
            ("603501.SS", "Will Semi / OmniVision — CMOS image sensors (豪威集团)",
             "豪威集团 — 图像传感器芯片"),
            ("300661.SZ", "SG Micro — analog IC leader (圣邦股份)",
             "圣邦股份 — 模拟芯片龙头"),
            ("688385.SS", "Fudan Micro — FPGA + security ICs (复旦微电)",
             "复旦微电 — 可编程逻辑与安全芯片"),
            ("688019.SS", "Anji Micro — CMP slurry / process materials (安集科技)",
             "安集科技 — 抛光液等半导体制程材料"),
            ("688249.SS", "Nexchip — display-driver specialty foundry (晶合集成)",
             "晶合集成 — 显示驱动特色工艺代工"),
        ],
    },
    "cn_ai_compute": {
        "name": "AI Compute & Optics", "name_zh": "AI算力与光模块",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "Optics, AI servers, switches and domestic accelerators tied to China AI capex.",
        "thesis_zh": "光模块、AI 服务器、交换机和国产加速器，受中国 AI 资本开支影响。",
        "members": [
            ("300308.SZ", "Zhongji Innolight — global 800G optical-module leader (中际旭创)",
             "中际旭创 — 全球800G光模块龙头"),
            ("300502.SZ", "Eoptolink — 800G optics fast-follower (新易盛)",
             "新易盛 — 800G光模块快速跟随者"),
            ("601138.SS", "Foxconn Industrial Internet — AI-server ODM scale (工业富联)",
             "工业富联 — AI服务器代工的规模优势"),
            ("688256.SS", "Cambricon — domestic training/inference accelerator",
             "寒武纪 — 国产训练与推理加速芯片"),
            ("000977.SZ", "Inspur — China's #1 AI-server vendor (浪潮信息)",
             "浪潮信息 — 中国第一大AI服务器厂商"),
            ("300394.SZ", "TFC Optical — optical passives / components (天孚通信)",
             "天孚通信 — 光无源器件与光组件"),
            ("002281.SZ", "Accelink — optical chips & modules (光迅科技)",
             "光迅科技 — 光芯片与光模块"),
            ("603019.SS", "Sugon — HPC / AI server + liquid cooling (中科曙光)",
             "中科曙光 — 高性能与AI服务器及液冷"),
            ("688041.SS", "Hygon — DCU compute for domestic AI clusters",
             "海光信息 — 面向国产AI集群的加速卡算力"),
            ("688795.SS", "Moore Threads — domestic AI / GPU accelerator (摩尔线程)",
             "摩尔线程 — 国产图形与AI加速芯片"),
            ("688802.SS", "MetaX — domestic GPGPU accelerator (沐曦股份)",
             "沐曦股份 — 国产通用图形加速卡"),
            ("300476.SZ", "Victory Giant — high-layer-count AI / HDI PCB (胜宏科技)",
             "胜宏科技 — 高层数AI与高密度互连电路板"),
            ("002463.SZ", "WUS Printed Circuit — AI-server PCB (沪电股份)",
             "沪电股份 — AI服务器印制电路板"),
            ("300620.SZ", "Advanced Fiber Resources — LiNbO3 modulators for 1.6T optics (光库科技)",
             "光库科技 — 用于1.6T光模块的铌酸锂调制器"),
            ("300442.SZ", "Range Intelligent Computing — AI data-centre / IDC operator (润泽科技)",
             "润泽科技 — AI数据中心运营商"),
            ("688702.SS", "Centec — Ethernet switch silicon (盛科通信)",
             "盛科通信 — 以太网交换芯片"),
            ("002837.SZ", "Envicool — AI data-centre liquid cooling (英维克)",
             "英维克 — AI数据中心液冷"),
        ],
    },
    "cn_consumer_elec": {
        "name": "Consumer Electronics", "name_zh": "消费电子",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": "515000.SS", "etf_proxy_note": "loose — broad Technology ETF",
        "thesis": "Apple/Android supply-chain names tied to smartphones, AI devices and hardware upgrades.",
        "thesis_zh": "苹果和安卓供应链公司，受智能手机、AI 设备和硬件升级影响。",
        "members": [
            ("002475.SZ", "Luxshare — top precision-assembly / connectors (立讯精密)",
             "立讯精密 — 精密组装与连接器龙头"),
            ("002241.SZ", "GoerTek — acoustics + AR/VR hardware (歌尔股份)",
             "歌尔股份 — 声学器件与虚拟／增强现实硬件"),
            ("300433.SZ", "Lens Technology — cover glass / casings (蓝思科技)",
             "蓝思科技 — 防护玻璃与结构机壳"),
            ("000725.SZ", "BOE — the dominant display panel maker (京东方)",
             "京东方 — 显示面板绝对龙头"),
            ("002384.SZ", "Dongshan Precision — FPC / PCB (东山精密)",
             "东山精密 — 柔性电路板与印制电路板"),
            ("002938.SZ", "Avary Holding — flex-PCB leader (鹏鼎控股)",
             "鹏鼎控股 — 柔性电路板龙头"),
            ("002600.SZ", "Lingyi iTech — functional parts / assembly (领益智造)",
             "领益智造 — 功能件与整机组装"),
            ("002273.SZ", "Crystal-Optech — optical filters / imaging (水晶光电)",
             "水晶光电 — 光学滤光片与成像元件"),
            ("002916.SZ", "Shennan Circuits — PCB + IC substrates (深南电路)",
             "深南电路 — 印制电路板与芯片封装基板"),
            ("000100.SZ", "TCL Technology — LCD / Mini-LED panels (TCL科技)",
             "TCL科技 — 液晶与新型显示面板"),
            ("002138.SZ", "Sunlord — inductors / passives (顺络电子)",
             "顺络电子 — 电感等被动元件"),
            ("300136.SZ", "Sunway Communication — RF / antenna modules (信维通信)",
             "信维通信 — 射频与天线模组"),
            ("300866.SZ", "Anker Innovations — global consumer-electronics brand (安克创新)",
             "安克创新 — 出海消费电子品牌"),
            ("688036.SS", "Transsion — emerging-market handset OEM (传音控股)",
             "传音控股 — 面向新兴市场的手机厂商"),
            ("002456.SZ", "OFILM — camera modules (欧菲光)",
             "欧菲光 — 摄像头模组"),
        ],
    },
    "cn_software": {
        "name": "Software & AI Apps", "name_zh": "软件与AI应用",
        "category": "Technology & AI", "category_zh": "科技与AI",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Domestic software and AI application names tied to IT localization and generative AI demand.",
        "thesis_zh": "国产软件和 AI 应用公司，受 IT 国产化和生成式 AI 需求影响。",
        "members": [
            ("688111.SS", "Kingsoft Office — WPS suite + AI copilot (金山办公)",
             "金山办公 — 办公软件套件与AI助手"),
            ("002230.SZ", "iFlytek — speech & LLM platform (科大讯飞)",
             "科大讯飞 — 语音识别与大模型平台"),
            ("600570.SS", "Hundsun — financial-institution software (恒生电子)",
             "恒生电子 — 金融机构信息化软件"),
            ("300454.SZ", "Sangfor — security / cloud infrastructure (深信服)",
             "深信服 — 网络安全与云基础设施"),
            ("600845.SS", "Baosight — industrial software (宝信软件)",
             "宝信软件 — 工业软件"),
            ("300033.SZ", "Hithink RoyalFlush — retail fintech data (同花顺)",
             "同花顺 — 面向散户的金融数据终端"),
            ("300418.SZ", "Kunlun Tech — AIGC / overseas internet (昆仑万维)",
             "昆仑万维 — 生成式AI与出海互联网"),
            ("600588.SS", "Yonyou — enterprise ERP / cloud (用友网络)",
             "用友网络 — 企业资源管理与云服务"),
            ("300496.SZ", "Thundersoft — edge-AI / OS / smart-cockpit software (中科创达)",
             "中科创达 — 端侧AI、操作系统与智能座舱软件"),
            ("688692.SS", "Dameng — domestic database, 信创 (达梦数据)",
             "达梦数据 — 国产数据库，信创受益"),
            ("301236.SZ", "iSoftStone — IT services / 信创 integrator (软通动力)",
             "软通动力 — 信息技术服务与信创集成商"),
            ("300339.SZ", "Hoperun — fintech software / HarmonyOS (润和软件)",
             "润和软件 — 金融科技软件与鸿蒙生态"),
            ("300803.SZ", "Compass — retail fintech terminal (指南针)",
             "指南针 — 面向散户的金融终端"),
            ("301269.SZ", "Empyrean — domestic EDA software (华大九天)",
             "华大九天 — 国产电子设计自动化软件"),
            ("601360.SS", "Qihoo 360 — security + AI-model platform (三六零)",
             "三六零 — 安全业务与AI大模型平台"),
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
            ("300750.SZ", "CATL — the global cell champion (宁德时代)",
             "宁德时代 — 全球动力电芯冠军"),
            ("002594.SZ", "BYD — batteries + the EV scale leader (比亚迪)",
             "比亚迪 — 电池叠加电动车规模龙头"),
            ("300014.SZ", "EVE Energy — cells + energy storage (亿纬锂能)",
             "亿纬锂能 — 电芯与储能"),
            ("002460.SZ", "Ganfeng Lithium — lithium resource / refining (赣锋锂业)",
             "赣锋锂业 — 锂资源与冶炼加工"),
            ("002466.SZ", "Tianqi Lithium — lithium upstream (天齐锂业)",
             "天齐锂业 — 锂上游资源"),
            ("300207.SZ", "Sunwoda — consumer + EV battery packs (欣旺达)",
             "欣旺达 — 消费与动力电池模组"),
            ("002074.SZ", "Gotion High-tech — LFP cells (国轩高科)",
             "国轩高科 — 磷酸铁锂电芯"),
            ("603659.SS", "Putailai — anode + coating equipment (璞泰来)",
             "璞泰来 — 负极材料与涂布设备"),
            ("002812.SZ", "Enjie — wet-process separator leader (恩捷股份)",
             "恩捷股份 — 湿法隔膜龙头"),
            ("002709.SZ", "Tinci Materials — electrolyte leader (天赐材料)",
             "天赐材料 — 电解液龙头"),
            ("300037.SZ", "Capchem — electrolyte leader (新宙邦)",
             "新宙邦 — 电解液龙头"),
            ("300919.SZ", "CNGR — ternary precursor leader (中伟新材)",
             "中伟新材 — 三元前驱体龙头"),
            ("300073.SZ", "Easpring — NCM cathode (当升科技)",
             "当升科技 — 三元正极材料"),   # removed 2026-07-01 — see REMOVED
            ("301358.SZ", "Hunan Yuneng — LFP cathode leader (湖南裕能)",
             "湖南裕能 — 磷酸铁锂正极龙头"),
            ("603799.SS", "Huayou Cobalt — cobalt / nickel + precursors (华友钴业)",
             "华友钴业 — 钴镍资源与前驱体"),
            ("002850.SZ", "Kedali — battery structural components (科达利)",
             "科达利 — 电池结构件"),
            ("002340.SZ", "GEM — battery recycling / precursors (格林美)",
             "格林美 — 电池回收与前驱体"),
        ],
    },
    "cn_solar": {
        "name": "Solar / Photovoltaics", "name_zh": "光伏",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515790.SS", "etf_proxy_note": "光伏ETF",
        "thesis": "Solar manufacturing chain from silicon to modules and inverters. Volume growth versus margin pressure.",
        "thesis_zh": "光伏制造链，从硅料到组件和逆变器。量增与利润率压力并存。",
        "members": [
            ("601012.SS", "LONGi — wafer + module leader (隆基绿能)",
             "隆基绿能 — 硅片与组件龙头"),
            ("600438.SS", "Tongwei — polysilicon + cells (通威股份)",
             "通威股份 — 多晶硅与电池片"),
            ("300274.SZ", "Sungrow — #1 inverter / storage (阳光电源)",
             "阳光电源 — 逆变器与储能第一"),
            ("002129.SZ", "TCL Zhonghuan — silicon wafers (TCL中环)",
             "TCL中环 — 光伏硅片"),
            ("688223.SS", "Jinko Solar — top global module shipper (晶科能源)",
             "晶科能源 — 全球组件出货龙头"),
            ("688303.SS", "Daqo — polysilicon pure-play (大全能源)",
             "大全能源 — 多晶硅纯正标的"),
            ("603806.SS", "Foster — EVA encapsulant film leader (福斯特)",
             "福斯特 — 光伏封装胶膜龙头"),
            ("688472.SS", "CSI Solar — modules + storage (阿特斯)",
             "阿特斯 — 组件与储能"),
            ("688599.SS", "Trina Solar — global module shipper (天合光能)",
             "天合光能 — 全球组件出货商"),
            ("002459.SZ", "JA Solar — top module maker (晶澳科技)",
             "晶澳科技 — 头部组件厂商"),
            ("300763.SZ", "Ginlong Solis — string inverters (锦浪科技)",
             "锦浪科技 — 组串式逆变器"),
            ("688390.SS", "GoodWe — inverters + storage (固德威)",
             "固德威 — 逆变器与储能"),
            ("605117.SS", "Deye — hybrid / micro-inverters + storage (德业股份)",
             "德业股份 — 混合与微型逆变器及储能"),
            ("300316.SZ", "Jingsheng — crystal-growth equipment (晶盛机电)",
             "晶盛机电 — 单晶生长设备"),
            ("300751.SZ", "Maxwell — HJT cell-process equipment (迈为股份)",
             "迈为股份 — 异质结电池工艺设备"),
        ],
    },
    "cn_autos": {
        "name": "Autos & NEV Makers", "name_zh": "汽车整车",
        "category": "New Energy & Autos", "category_zh": "新能源与汽车",
        "etf_proxy": "515250.SS", "etf_proxy_note": "智能汽车ETF",
        "thesis": "China automakers and suppliers tied to EV adoption, intelligent driving and exports.",
        "thesis_zh": "中国整车和供应商，受电动车渗透、智能驾驶和出口影响。",
        "members": [
            ("002594.SZ", "BYD — the NEV scale + export leader (比亚迪)",
             "比亚迪 — 新能源车规模与出口龙头"),
            ("601633.SS", "Great Wall Motor — SUV/pickup + export (长城汽车)",
             "长城汽车 — 越野车、皮卡与出口"),
            ("000625.SZ", "Changan — fast NEV transition (长安汽车)",
             "长安汽车 — 新能源转型提速"),
            ("600104.SS", "SAIC Motor — largest legacy OEM (上汽集团)",
             "上汽集团 — 规模最大的传统整车厂"),
            ("601127.SS", "Seres — Huawei AITO partner (赛力斯)",
             "赛力斯 — 华为问界合作方"),
            ("601238.SS", "GAC Group — JV + Aion NEV (广汽集团)",
             "广汽集团 — 合资板块叠加埃安新能源"),
            ("600660.SS", "Fuyao Glass — global auto-glass leader (福耀玻璃)",
             "福耀玻璃 — 全球汽车玻璃龙头"),
            ("601689.SS", "Tuopu — chassis + thermal, Tesla supplier (拓普集团)",
             "拓普集团 — 底盘与热管理，特斯拉供应商"),
            ("002920.SZ", "Desay SV — smart-cockpit / ADAS (德赛西威)",
             "德赛西威 — 智能座舱与辅助驾驶"),
            ("000338.SZ", "Weichai Power — heavy-duty powertrain (潍柴动力)",
             "潍柴动力 — 重卡动力总成"),
            ("600741.SS", "Huayu Automotive — the largest parts group (华域汽车)",
             "华域汽车 — 规模最大的零部件集团"),
            ("601799.SS", "Xingyu — automotive lighting (星宇股份)",
             "星宇股份 — 汽车车灯"),
            ("002126.SZ", "Yinlun — thermal management (银轮股份)",
             "银轮股份 — 汽车热管理"),
            ("600066.SS", "Yutong Bus — buses + EV export (宇通客车)",
             "宇通客车 — 客车与电动客车出口"),
            ("000800.SZ", "FAW Jiefang — heavy-truck OEM (一汽解放)",
             "一汽解放 — 重卡整车厂"),
            ("600418.SS", "JAC — OEM, Huawei / NIO partner (江淮汽车)",
             "江淮汽车 — 整车厂，华为与蔚来合作方"),
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
            ("600760.SS", "AVIC Shenyang — fighter-jet prime (中航沈飞)",
             "中航沈飞 — 战斗机主机厂"),
            ("302132.SZ", "AVIC Chengdu — J-series fighters (中航成飞)",
             "中航成飞 — 歼击机系列主机厂"),
            ("600893.SS", "AECC Aviation Power — aero-engines (航发动力)",
             "航发动力 — 航空发动机"),
            ("000768.SZ", "AVIC Xi'an — bombers / transports (中航西飞)",
             "中航西飞 — 轰炸机与运输机"),
            ("002179.SZ", "Jonhon — defense connectors (中航光电)",
             "中航光电 — 军用连接器"),
            ("600150.SS", "CSSC — shipbuilding champion (中国船舶)",
             "中国船舶 — 造船业冠军"),
            ("600118.SS", "China Spacesat — satellites (中国卫星)",
             "中国卫星 — 卫星制造与应用"),
            ("002414.SZ", "Guide Infrared — thermal imaging (高德红外)",
             "高德红外 — 红外热成像"),
            ("600372.SS", "AVIC Airborne Systems — avionics (中航机载)",
             "中航机载 — 航空电子系统"),
            ("600879.SS", "Aerospace Times Electronics — missiles / electronics (航天电子)",
             "航天电子 — 导弹与航天电子"),
            ("002025.SZ", "Guizhou Space Appliance — mil connectors (航天电器)",
             "航天电器 — 航天与军用继电器、连接器"),
            ("688297.SS", "AVIC UAS — military drones (中无人机)",
             "中无人机 — 军用无人机"),
            ("600562.SS", "Glarun — defense radar (国睿科技)",
             "国睿科技 — 军用雷达"),   # removed 2026-07-01 — see REMOVED
            ("000733.SZ", "China Zhenhua — military electronic components (振华科技)",
             "振华科技 — 军用电子元器件"),
        ],
    },
    "cn_robotics": {
        "name": "Robotics & Automation", "name_zh": "机器人与自动化",
        "category": "Advanced Manufacturing", "category_zh": "高端制造",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Automation and humanoid-robot supply chain: drives, reducers, controllers and parts.",
        "thesis_zh": "自动化和人形机器人供应链：驱动、减速器、控制器和零部件。",
        "members": [
            ("300124.SZ", "Inovance — servo / motion-control leader (汇川技术)",
             "汇川技术 — 伺服与运动控制龙头"),
            ("688017.SS", "Leader Drive — harmonic reducers (绿的谐波)",
             "绿的谐波 — 谐波减速器"),
            ("002747.SZ", "Estun — industrial robots (埃斯顿)",
             "埃斯顿 — 工业机器人整机"),
            ("300024.SZ", "Siasun — robotics pioneer (机器人/新松)",
             "新松机器人 — 国内机器人行业先行者"),
            ("002472.SZ", "Shuanghuan — precision gears / RV reducers (双环传动)",
             "双环传动 — 精密齿轮与旋转矢量减速器"),
            ("002050.SZ", "Sanhua — thermal mgmt + humanoid actuators (三花智控)",
             "三花智控 — 热管理与人形机器人执行器"),
            ("601689.SS", "Tuopu — humanoid linear-actuator supplier (拓普集团)",
             "拓普集团 — 人形机器人直线执行器供应商"),
            ("601100.SS", "Hengli Hydraulic — actuators / electric cylinders (恒立液压)",
             "恒立液压 — 液压执行器与电动缸"),
            ("002046.SZ", "Sinomach Precision — high-precision bearings (国机精工)",
             "国机精工 — 高精度轴承"),
            ("688322.SS", "Orbbec — 3D vision sensors for robots (奥比中光)",
             "奥比中光 — 机器人三维视觉传感器"),
            ("002851.SZ", "Megmeet — motion / power-electronics control (麦格米特)",
             "麦格米特 — 运动控制与电力电子"),
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
            ("600519.SS", "Kweichow Moutai — the ultra-premium anchor (贵州茅台)",
             "贵州茅台 — 超高端白酒的定海神针"),
            ("000858.SZ", "Wuliangye — the #2 premium brand (五粮液)",
             "五粮液 — 高端白酒第二品牌"),
            ("000568.SZ", "Luzhou Laojiao — premium + mid-range (泸州老窖)",
             "泸州老窖 — 高端与中端并重"),
            ("600809.SS", "Shanxi Fenjiu — fast-growing fragrance baijiu (山西汾酒)",
             "山西汾酒 — 高增长的清香型白酒"),
            ("002304.SZ", "Yanghe — east-China leader (洋河股份)",
             "洋河股份 — 华东市场龙头"),
            ("000596.SZ", "Gujing Gong — regional premium (古井贡酒)",
             "古井贡酒 — 区域高端品牌"),
            ("603369.SS", "King's Luck — fast-growing Jiangsu baijiu (今世缘)",
             "今世缘 — 高增长的江苏白酒"),
        ],
    },
    "cn_appliances": {
        "name": "Home Appliances", "name_zh": "家电",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "White-goods and appliance leaders tied to trade-in stimulus, exports and property after-cycle.",
        "thesis_zh": "白电和家电龙头，受以旧换新、出口和地产后周期影响。",
        "members": [
            ("000333.SZ", "Midea — diversified appliance + robotics (美的集团)",
             "美的集团 — 多元家电兼具机器人业务"),
            ("000651.SZ", "Gree — air-conditioning leader (格力电器)",
             "格力电器 — 空调龙头"),
            ("600690.SS", "Haier Smart Home — global premium brands (海尔智家)",
             "海尔智家 — 全球高端家电品牌矩阵"),
            ("000921.SZ", "Hisense Home Appliances — AC + white goods (海信家电)",
             "海信家电 — 空调与白色家电"),
            ("600060.SS", "Hisense Visual — TV / display (海信视像)",
             "海信视像 — 电视与显示终端"),
            ("002032.SZ", "Supor — small kitchen appliances (苏泊尔)",
             "苏泊尔 — 厨房小家电"),
            ("603486.SS", "Ecovacs — robot vacuums / smart home (科沃斯)",
             "科沃斯 — 扫地机器人与智能家居"),
            ("600839.SS", "Sichuan Changhong — TV + white goods (四川长虹)",
             "四川长虹 — 电视与白色家电"),
        ],
    },
    "cn_food_bev": {
        "name": "Food & Beverage", "name_zh": "食品饮料",
        "category": "Consumer & Brands", "category_zh": "核心消费",
        "etf_proxy": "159928.SZ", "etf_proxy_note": "消费ETF — staples",
        "thesis": "Staple food and beverage leaders. Defensive read on mass-market demand and input costs.",
        "thesis_zh": "大众食品饮料龙头。防御性观察大众需求和成本。",
        "members": [
            ("600887.SS", "Yili — the dairy leader (伊利股份)",
             "伊利股份 — 乳制品龙头"),
            ("603288.SS", "Haitian — soy sauce / condiments king (海天味业)",
             "海天味业 — 酱油与调味品之王"),
            ("605499.SS", "Eastroc Beverage — energy-drink growth (东鹏饮料)",
             "东鹏饮料 — 能量饮料高增长"),
            ("300999.SZ", "Arawana — cooking oil / staples (金龙鱼)",
             "金龙鱼 — 食用油与厨房食品"),
            ("000895.SZ", "Shuanghui — meat processing leader (双汇发展)",
             "双汇发展 — 肉制品加工龙头"),
            ("600600.SS", "Tsingtao Brewery — premium beer (青岛啤酒)",
             "青岛啤酒 — 高端啤酒"),
            ("000729.SZ", "Yanjing Brewery — beer (燕京啤酒)",
             "燕京啤酒 — 啤酒"),
            ("600298.SS", "Angel Yeast — yeast / food ingredients (安琪酵母)",
             "安琪酵母 — 酵母与食品配料"),
            ("603345.SS", "Anjoy Foods — frozen prepared foods (安井食品)",
             "安井食品 — 速冻预制食品"),   # removed 2026-07-01 — see REMOVED
            ("603156.SS", "Yangyuan — Six Walnuts plant-protein drink (养元饮品)",
             "养元饮品 — 六个核桃植物蛋白饮料"),
            ("002311.SZ", "Haid Group — animal feed / aquaculture (海大集团)",
             "海大集团 — 饲料与水产养殖"),
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
            ("603259.SS", "WuXi AppTec — the CXO bellwether (药明康德)",
             "药明康德 — 医药研发外包的风向标"),
            ("600276.SS", "Hengrui — the innovative-drug leader (恒瑞医药)",
             "恒瑞医药 — 创新药龙头"),
            ("688235.SS", "BeiGene — global oncology biotech (百济神州)",
             "百济神州 — 全球化肿瘤生物药企"),
            ("300759.SZ", "Pharmaron — pre-clinical CRO (康龙化成)",
             "康龙化成 — 临床前研发外包"),
            ("002821.SZ", "Asymchem — small-molecule CDMO (凯莱英)",
             "凯莱英 — 小分子定制研发与生产"),
            ("688506.SS", "Baili Tianheng — ADC out-licensing story (百利天恒)",
             "百利天恒 — 抗体偶联药物对外授权故事"),
            ("688331.SS", "RemeGen — ADC / autoimmune biotech (荣昌生物)",
             "荣昌生物 — 抗体偶联与自身免疫生物药"),
            ("002422.SZ", "Kelun — drugs + ADC pipeline (科伦药业)",
             "科伦药业 — 仿制药叠加抗体偶联管线"),
            ("300347.SZ", "Tigermed — clinical CRO (泰格医药)",
             "泰格医药 — 临床研究外包"),
            ("688428.SS", "InnoCare — innovative-oncology biotech (诺诚健华)",
             "诺诚健华 — 创新肿瘤生物药"),
            ("688180.SS", "Junshi Biosciences — PD-1 / antibody biotech (君实生物)",
             "君实生物 — 免疫检查点与抗体药物"),
            ("688578.SS", "Allist — EGFR lung-cancer drugs (艾力斯)",
             "艾力斯 — 肺癌靶向药"),
            ("600196.SS", "Fosun Pharma — pharma + CXO + innovation (复星医药)",
             "复星医药 — 制药、外包与创新并举"),
            ("603087.SS", "Gan & Lee — domestic insulin franchise (甘李药业)",
             "甘李药业 — 国产胰岛素龙头"),
        ],
    },
    "cn_med_devices": {
        "name": "Medical Devices & TCM", "name_zh": "医疗器械与中药",
        "category": "Healthcare", "category_zh": "医药健康",
        "etf_proxy": "512170.SS", "etf_proxy_note": "医疗ETF",
        "thesis": "Medical devices, services and TCM brands tied to domestic substitution and defensive health demand.",
        "thesis_zh": "医疗器械、服务和中药品牌，受国产替代和防御性医疗需求影响。",
        "members": [
            ("300760.SZ", "Mindray — the medical-device leader (迈瑞医疗)",
             "迈瑞医疗 — 医疗器械龙头"),
            ("688271.SS", "United Imaging — high-end imaging systems (联影医疗)",
             "联影医疗 — 高端医学影像设备"),
            ("300015.SZ", "Aier Eye — ophthalmology hospital chain (爱尔眼科)",
             "爱尔眼科 — 眼科连锁医院"),
            ("000538.SZ", "Yunnan Baiyao — branded TCM franchise (云南白药)",
             "云南白药 — 品牌中药矩阵"),
            ("600436.SS", "Pientzehuang — ultra-premium TCM (片仔癀)",
             "片仔癀 — 超高端中药"),
            ("000999.SZ", "CR Sanjiu — OTC / TCM brands (华润三九)",
             "华润三九 — 非处方药与中药品牌"),
            ("600085.SS", "Tongrentang — heritage TCM brand (同仁堂)",
             "同仁堂 — 老字号中药品牌"),
            ("000963.SZ", "Huadong Medicine — pharma + aesthetics (华东医药)",
             "华东医药 — 制药与医美双轮"),
            ("688617.SS", "APT Medical — electrophysiology devices (惠泰医疗)",
             "惠泰医疗 — 电生理介入器械"),
            ("300832.SZ", "New Industries — chemiluminescence IVD (新产业)",
             "新产业 — 化学发光体外诊断"),
            ("688301.SS", "iRay — X-ray flat-panel detectors (奕瑞科技)",
             "奕瑞科技 — 数字化射线平板探测器"),
            ("300896.SZ", "Imeik — medical-aesthetics filler leader (爱美客)",
             "爱美客 — 医美填充剂龙头"),
            ("000423.SZ", "Dong-E-E-Jiao — branded ejiao TCM (东阿阿胶)",
             "东阿阿胶 — 阿胶品牌中药"),
            ("600332.SS", "Baiyunshan — pharma + TCM brands (白云山)",
             "白云山 — 制药与中药品牌"),
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
            ("601398.SS", "ICBC — the largest state bank (工商银行)",
             "工商银行 — 规模最大的国有大行"),
            ("601939.SS", "China Construction Bank (建设银行)",
             "建设银行 — 国有大行，基建与按揭主力"),
            ("601288.SS", "Agricultural Bank of China (农业银行)",
             "农业银行 — 国有大行，县域网点最广"),
            ("601988.SS", "Bank of China (中国银行)",
             "中国银行 — 国有大行，跨境业务见长"),
            ("600036.SS", "China Merchants Bank — premier retail bank (招商银行)",
             "招商银行 — 零售银行标杆"),
            ("601166.SS", "Industrial Bank (兴业银行)",
             "兴业银行 — 同业与对公见长的股份行"),
            ("600000.SS", "SPD Bank (浦发银行)",
             "浦发银行 — 上海系股份制银行"),
            ("601328.SS", "Bank of Communications (交通银行)",
             "交通银行 — 国有大行，高股息标的"),
            ("601658.SS", "Postal Savings Bank — retail franchise (邮储银行)",
             "邮储银行 — 零售存款与县域网络"),
            ("000001.SZ", "Ping An Bank — retail growth (平安银行)",
             "平安银行 — 零售转型成长"),
            ("601998.SS", "CITIC Bank — joint-stock lender (中信银行)",
             "中信银行 — 股份制银行"),
            ("600016.SS", "Minsheng Bank — joint-stock lender (民生银行)",
             "民生银行 — 股份制银行，民企客群"),
            ("601818.SS", "Everbright Bank — joint-stock lender (光大银行)",
             "光大银行 — 股份制银行"),
            ("002142.SZ", "Bank of Ningbo — top-tier city bank (宁波银行)",
             "宁波银行 — 头部城商行"),
            ("600919.SS", "Bank of Jiangsu — leading city bank (江苏银行)",
             "江苏银行 — 领先城商行"),
            ("601169.SS", "Bank of Beijing — largest city bank (北京银行)",
             "北京银行 — 规模最大的城商行"),
            ("601009.SS", "Bank of Nanjing — city bank (南京银行)",
             "南京银行 — 江苏城商行"),
            ("601229.SS", "Bank of Shanghai — city bank (上海银行)",
             "上海银行 — 上海城商行"),
        ],
    },
    "cn_brokers": {
        "name": "Brokers & Securities", "name_zh": "券商",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": "512880.SS", "etf_proxy_note": "证券ETF",
        "thesis": "Brokerages and trading platforms tied to turnover, margin balances and capital-market activity.",
        "thesis_zh": "券商和交易平台，受成交额、两融余额和资本市场活跃度影响。",
        "members": [
            ("600030.SS", "CITIC Securities — the #1 broker (中信证券)",
             "中信证券 — 券商龙头"),
            ("300059.SZ", "East Money — retail fintech-broker (东方财富)",
             "东方财富 — 互联网零售券商"),
            ("601688.SS", "Huatai Securities (华泰证券)",
             "华泰证券 — 头部券商，财富管理见长"),
            ("601211.SS", "Guotai Junan — post-Haitong merger (国泰海通)",
             "国泰海通 — 合并海通后的头部券商"),
            ("600999.SS", "China Merchants Securities (招商证券)",
             "招商证券 — 头部综合券商"),
            ("000776.SZ", "GF Securities (广发证券)",
             "广发证券 — 头部券商，资管见长"),
            ("601066.SS", "CSC Financial (中信建投)",
             "中信建投 — 投行业务见长的头部券商"),
            ("601995.SS", "CICC — top investment bank (中金公司)",
             "中金公司 — 顶级投资银行"),
            ("600958.SS", "Orient Securities (东方证券)",
             "东方证券 — 中型综合券商，资管见长"),
            ("000166.SZ", "Shenwan Hongyuan (申万宏源)",
             "申万宏源 — 综合券商"),
            ("601881.SS", "China Galaxy Securities (中国银河)",
             "中国银河 — 经纪业务见长的国有券商"),
            ("002736.SZ", "Guosen Securities (国信证券)",
             "国信证券 — 经纪与投行综合券商"),
            ("000783.SZ", "Changjiang Securities (长江证券)",
             "长江证券 — 研究见长的中型券商"),
            ("601788.SS", "Everbright Securities (光大证券)",
             "光大证券 — 综合券商"),
            ("601377.SS", "Industrial Securities (兴业证券)",
             "兴业证券 — 综合券商，公募资管见长"),
        ],
    },
    "cn_insurers": {
        "name": "Insurers", "name_zh": "保险",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Life and P&C insurers tied to equity markets, yields and new-business value.",
        "thesis_zh": "寿险和财险公司，受股市、利率和新业务价值影响。",
        "members": [
            ("601318.SS", "Ping An — the integrated insurance leader (中国平安)",
             "中国平安 — 综合金融保险龙头"),
            ("601628.SS", "China Life — largest life insurer (中国人寿)",
             "中国人寿 — 规模最大的寿险公司"),
            ("601601.SS", "China Pacific Insurance (中国太保)",
             "中国太保 — 寿险与财险并重"),
            ("601319.SS", "PICC — P&C leader (中国人保)",
             "中国人保 — 财产险龙头"),
            ("601336.SS", "New China Life (新华保险)",
             "新华保险 — 寿险，权益弹性大"),
        ],
    },
    "cn_soe_value": {
        "name": "SOE Blue Chips (中特估)", "name_zh": "中特估·央企",
        "category": "Financials & Value", "category_zh": "金融与价值",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Central SOE value basket: oil, telecom, infrastructure and utilities with high dividends.",
        "thesis_zh": "央企价值篮子：石油、电信、基建和公用事业，高股息特征。",
        "members": [
            ("601857.SS", "PetroChina — oil & gas major (中国石油)",
             "中国石油 — 油气巨头"),
            ("600028.SS", "Sinopec — refining / chemicals major (中国石化)",
             "中国石化 — 炼化与化工巨头"),
            ("600938.SS", "CNOOC — offshore E&P, low-cost barrels (中国海油)",
             "中国海油 — 海上勘探开发，低成本原油"),
            ("600941.SS", "China Mobile — carrier + dividend anchor (中国移动)",
             "中国移动 — 运营商与红利压舱石"),
            ("601728.SS", "China Telecom (中国电信)",
             "中国电信 — 运营商，云与算力业务"),
            ("600050.SS", "China Unicom (中国联通)",
             "中国联通 — 运营商，混改标的"),
            ("601668.SS", "China State Construction (中国建筑)",
             "中国建筑 — 房建与基建总承包龙头"),
            ("601390.SS", "China Railway Group (中国中铁)",
             "中国中铁 — 铁路与基建央企"),
            ("601186.SS", "China Railway Construction (中国铁建)",
             "中国铁建 — 铁路与市政基建央企"),
            ("600900.SS", "Yangtze Power — hydro / dividend (长江电力)",
             "长江电力 — 水电与高股息"),
            ("601800.SS", "China Communications Construction — infra major (中国交建)",
             "中国交建 — 交通基建央企"),
            ("601618.SS", "MCC — metallurgical / infra SOE (中国中冶)",
             "中国中冶 — 冶金工程与基建央企"),
            ("601669.SS", "PowerChina — power-grid / infra SOE (中国电建)",
             "中国电建 — 电网与电力基建央企"),
            ("601766.SS", "CRRC — rolling-stock champion (中国中车)",
             "中国中车 — 轨道交通装备冠军"),
            ("601117.SS", "China National Chemical Eng. (中国化学)",
             "中国化学 — 化学工程建设央企"),
            ("601919.SS", "COSCO Shipping Holdings — container shipping SOE (中远海控)",
             "中远海控 — 集装箱航运央企"),
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
            ("601899.SS", "Zijin Mining — gold + copper giant (紫金矿业)",
             "紫金矿业 — 黄金与铜双料巨头"),
            ("600547.SS", "Shandong Gold — pure-play producer (山东黄金)",
             "山东黄金 — 纯正黄金生产商"),
            ("600489.SS", "Zhongjin Gold — SOE producer (中金黄金)",
             "中金黄金 — 央企黄金生产商"),
            ("600988.SS", "Chifeng Gold — fast-growing miner (赤峰黄金)",
             "赤峰黄金 — 高成长金矿商"),
            ("002155.SZ", "Hunan Gold — gold + antimony/tungsten (湖南黄金)",
             "湖南黄金 — 黄金兼具锑与钨"),
            ("000975.SZ", "Shanjin International — gold producer (山金国际)",
             "山金国际 — 黄金生产商"),
        ],
    },
    "cn_metals": {
        "name": "Industrial Metals", "name_zh": "有色金属",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "512400.SS", "etf_proxy_note": "有色金属ETF",
        "thesis": "Copper, aluminium and industrial metals producers tied to global growth and green capex.",
        "thesis_zh": "铜、铝和工业金属生产商，受全球增长和绿色资本开支影响。",
        "members": [
            ("603993.SS", "CMOC — copper / cobalt / moly (洛阳钼业)",
             "洛阳钼业 — 铜、钴与钼资源"),
            ("600362.SS", "Jiangxi Copper — copper leader (江西铜业)",
             "江西铜业 — 铜冶炼龙头"),
            ("601600.SS", "Chalco — aluminium major (中国铝业)",
             "中国铝业 — 电解铝巨头"),
            ("000807.SZ", "Yunnan Aluminium — green-power smelting (云铝股份)",
             "云铝股份 — 绿电电解铝"),
            ("000630.SZ", "Tongling Nonferrous — copper (铜陵有色)",
             "铜陵有色 — 铜冶炼与加工"),
            ("002379.SZ", "Shandong Hongqiao — top aluminium (宏桥/魏桥)",
             "魏桥系铝业 — 电解铝产能居前"),
            ("002532.SZ", "Tianshan Aluminium — integrated smelter (天山铝业)",
             "天山铝业 — 一体化电解铝"),
            ("601899.SS", "Zijin Mining — copper / gold giant (紫金矿业)",
             "紫金矿业 — 铜与黄金巨头"),
            ("000878.SZ", "Yunnan Copper (云南铜业)",
             "云南铜业 — 云南资源的铜冶炼商"),
            ("601168.SS", "Western Mining — copper / zinc / lead (西部矿业)",
             "西部矿业 — 铜、锌与铅资源"),
            ("601958.SS", "Jinduicheng Molybdenum — moly (金钼股份)",
             "金钼股份 — 钼资源龙头"),
            ("000960.SZ", "Yunnan Tin — global tin leader (锡业股份)",
             "锡业股份 — 全球锡业龙头"),
            ("000060.SZ", "Zhongjin Lingnan — lead / zinc (中金岭南)",
             "中金岭南 — 铅锌资源"),
        ],
    },
    "cn_rare_earth": {
        "name": "Rare Earth & Magnets", "name_zh": "稀土永磁",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "512400.SS", "etf_proxy_note": "loose — broad nonferrous ETF",
        "thesis": "Rare-earth and magnet makers tied to EV motors, wind, robotics and export controls.",
        "thesis_zh": "稀土和磁材公司，受电机、风电、机器人和出口管制影响。",
        "members": [
            ("600111.SS", "Northern Rare Earth — the resource giant (北方稀土)",
             "北方稀土 — 稀土资源巨头"),
            ("000831.SZ", "China Rare Earth — SOE consolidator (中国稀土)",
             "中国稀土 — 央企稀土整合平台"),
            ("300748.SZ", "JL MAG — NdFeB magnets leader (金力永磁)",
             "金力永磁 — 钕铁硼磁材龙头"),
            ("600392.SS", "Shenghe Resources — rare-earth trade/processing (盛和资源)",
             "盛和资源 — 稀土贸易与分离加工"),
            ("600549.SS", "Xiamen Tungsten — tungsten + rare earth (厦门钨业)",
             "厦门钨业 — 钨资源兼具稀土"),
            ("000657.SZ", "China Tungsten & Hightech — tungsten (中钨高新)",
             "中钨高新 — 钨深加工与硬质合金"),
            ("002056.SZ", "DMEGC — NdFeB + ferrite magnets (横店东磁)",
             "横店东磁 — 钕铁硼与铁氧体磁材"),
            ("002378.SZ", "Zhangyuan Tungsten — tungsten (章源钨业)",
             "章源钨业 — 钨资源与加工"),
            ("600259.SS", "Rising Nonferrous — rare-earth processing (中稀有色)",
             "中稀有色 — 稀土分离加工"),
        ],
    },
    "cn_coal": {
        "name": "Coal", "name_zh": "煤炭",
        "category": "Cyclicals & Resources", "category_zh": "周期与资源",
        "etf_proxy": "515220.SS", "etf_proxy_note": "煤炭ETF",
        "thesis": "Coal producers with high payout and power-demand exposure.",
        "thesis_zh": "煤炭生产商，高派息并受电力需求影响。",
        "members": [
            ("601088.SS", "China Shenhua — integrated coal/power dividend anchor (中国神华)",
             "中国神华 — 煤电一体化的红利压舱石"),
            ("601225.SS", "Shaanxi Coal — low-cost thermal coal (陕西煤业)",
             "陕西煤业 — 低成本动力煤"),
            ("601898.SS", "China Coal Energy (中煤能源)",
             "中煤能源 — 煤炭央企，煤化工并举"),
            ("600188.SS", "Yankuang Energy — coal + chemicals (兖矿能源)",
             "兖矿能源 — 煤炭与煤化工"),
            ("601699.SS", "Lu'an Environmental — coking/thermal (潞安环能)",
             "潞安环能 — 喷吹煤与动力煤"),
            ("000983.SZ", "Shanxi Coking Coal (山西焦煤)",
             "山西焦煤 — 炼焦煤龙头"),
            ("600985.SS", "Huaibei Mining — coking coal (淮北矿业)",
             "淮北矿业 — 炼焦煤兼具煤化工"),
            ("601001.SS", "Jinkong Coal — Shanxi thermal coal (晋控煤业)",
             "晋控煤业 — 山西动力煤"),
            ("600348.SS", "Huayang — anthracite / new-energy materials (华阳股份)",
             "华阳股份 — 无烟煤与新能源材料"),
            ("600925.SS", "Jiangsu Xukuang Energy — coal + power (苏能股份)",
             "苏能股份 — 煤炭与电力一体化"),
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
        for ticker, rationale, rationale_zh in b["members"]:
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
                            "name_zh": zh_name(bid, ticker), "rationale": rationale,
                            "rationale_zh": rationale_zh})
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
