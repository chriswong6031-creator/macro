"""Seed data/baskets_canada/membership.json — curated S&P/TSX thematic baskets.

The Canada analogue of scripts/seed_china_baskets.py. Defines the recognizable TSX themes —
the Big-Five banks, gold miners, silver & royalty names, oil & gas producers, pipelines,
uranium, base metals, rails, tech, utilities/renewables, telecom, staples/retail and REITs —
and their equal-weight member tickers, then materialises the membership schema
engine.baskets_canada.compute_canada_baskets() consumes.

Member names are filled from data/canada_search/members.parquet and EVERY ticker is validated
against the canada_search close cache (fail loud on a miss). Benchmark = S&P/TSX Composite
(XIC.TO); most baskets get a clean iShares sector-ETF cross-check. (The once-iconic cannabis
theme is intentionally omitted — only one name survives in the Composite.) Re-runnable:
`python -m scripts.seed_canada_baskets`.

HONEST BY CONSTRUCTION: membership is curated today with knowledge of the period, so the ~5y
series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest, not a buy list.
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
log = logging.getLogger("seed_canada_baskets")

SEED = "2021-06-14"   # start of the canada_search close cache

BASKETS: dict[str, dict] = {
    # ─────────────────────────────── Financials · 金融 ───────────────────────────────
    "ca_banks": {
        "name": "Big Banks", "name_zh": "大型银行",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": "ZEB.TO", "etf_proxy_note": "BMO Equal Weight Banks ETF",
        "thesis": "The backbone of the TSX — the Big-Five chartered banks plus the alt-lenders. Oligopoly economics, fat dividends and a direct read on Canadian credit, mortgages and net-interest-margin. The index's largest single bloc.",
        "thesis_zh": "多伦多交易所的支柱 — 五大特许银行加另类贷款机构。寡头经济、丰厚分红，直接反映加拿大信贷、按揭与净息差。指数中最大的单一板块。",
        "members": [
            ("RY.TO", "Royal Bank — the largest Canadian bank"),
            ("TD.TO", "TD Bank — retail + US franchise"),
            ("BMO.TO", "Bank of Montreal"),
            ("CM.TO", "CIBC"),
            ("BNS.TO", "Scotiabank — LatAm exposure"),
            ("EQB.TO", "EQB — digital challenger bank"),
            ("LB.TO", "Laurentian Bank"),
        ],
    },
    "ca_insurers": {
        "name": "Insurers", "name_zh": "保险",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The big lifecos and P&C insurers — earnings and book value geared to equity markets, long-bond yields and Asia/US growth. A rate-sensitive financial sleeve distinct from the banks.",
        "thesis_zh": "大型寿险与财险公司 — 利润与净资产挂钩权益市场、长债收益率及亚洲/美国增长。区别于银行、对利率敏感的金融板块。",
        "members": [
            ("MFC.TO", "Manulife — life + Asia / Global WAM"),
            ("SLF.TO", "Sun Life — life + asset management"),
            ("GWO.TO", "Great-West Lifeco"),
            ("IFC.TO", "Intact Financial — P&C leader"),
            ("IAG.TO", "iA Financial"),
            ("FFH.TO", "Fairfax — insurance + investments"),
        ],
    },
    "ca_asset_mgrs": {
        "name": "Asset Managers & Alternatives", "name_zh": "资产管理与另类投资",
        "category": "Financials", "category_zh": "金融",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Canada's alternative-asset and holding-company complex — the Brookfield empire, Power, Onex, the fund managers and the exchange. Levered to fee-bearing capital, deal flow and private-market valuations.",
        "thesis_zh": "加拿大的另类资产与控股公司集群 — 博枫体系、Power、Onex、基金管理人与交易所。受管理费资本、交易活动与私募市场估值驱动。",
        "members": [
            ("BN.TO", "Brookfield Corp — alternatives flagship"),
            ("BAM.TO", "Brookfield Asset Management — pure-play fees"),
            ("POW.TO", "Power Corp of Canada"),
            ("IGM.TO", "IGM Financial — wealth/asset mgmt"),
            ("ONEX.TO", "Onex — private equity"),
            ("X.TO", "TMX Group — the exchange operator"),
            ("SII.TO", "Sprott — precious-metals asset manager"),
        ],
    },
    # ───────────────────────────── Precious Metals · 贵金属 ─────────────────────────────
    "ca_gold": {
        "name": "Gold Miners", "name_zh": "黄金矿业",
        "category": "Precious Metals", "category_zh": "贵金属",
        "etf_proxy": "XGD.TO", "etf_proxy_note": "iShares Gold Producers ETF",
        "thesis": "The TSX's signature theme — senior and mid-tier gold producers levered to the bullion price, central-bank buying and the real-rate / de-dollarization narrative. High operating leverage to gold.",
        "thesis_zh": "多交所的标志性主题 — 大型与中型金矿生产商，受金价、央行购金与实际利率/去美元化叙事驱动。对金价具高经营杠杆。",
        "members": [
            ("AEM.TO", "Agnico Eagle — top-tier senior producer"),
            ("ABX.TO", "Barrick — global gold/copper major"),
            ("K.TO", "Kinross Gold"),
            ("AGI.TO", "Alamos Gold"),
            ("BTO.TO", "B2Gold"),
            ("ELD.TO", "Eldorado Gold"),
            ("IMG.TO", "IAMGOLD"),
            ("LUG.TO", "Lundin Gold — Fruta del Norte"),
        ],
    },
    "ca_silver_royalty": {
        "name": "Silver & Royalties", "name_zh": "白银与特许权金",
        "category": "Precious Metals", "category_zh": "贵金属",
        "etf_proxy": "XGD.TO", "etf_proxy_note": "loose — Gold Producers ETF",
        "thesis": "The capital-light royalty/streaming names plus the silver producers — leverage to precious-metals prices with lower operating risk (royalties) or higher beta (silver). A complement to the gold-miner basket.",
        "thesis_zh": "轻资产的特许权/流式金融公司加白银生产商 — 以更低经营风险（特许权）或更高弹性（白银）押注贵金属价格。黄金矿业篮子的补充。",
        "members": [
            ("WPM.TO", "Wheaton Precious Metals — streaming leader"),
            ("FNV.TO", "Franco-Nevada — royalty bellwether"),
            ("OR.TO", "Osisko / OR Royalties"),
            ("TFPM.TO", "Triple Flag Precious Metals"),
            ("PAAS.TO", "Pan American Silver"),
            ("AG.TO", "First Majestic Silver"),
            ("FVI.TO", "Fortuna Mining"),
        ],
    },
    # ─────────────────────────────── Energy · 能源 ───────────────────────────────
    "ca_oil_gas": {
        "name": "Oil & Gas Producers", "name_zh": "油气生产",
        "category": "Energy", "category_zh": "能源",
        "etf_proxy": "XEG.TO", "etf_proxy_note": "iShares S&P/TSX Energy ETF",
        "thesis": "The oil-sands integrators and the gas/light-oil E&Ps — heavy free-cash-flow returned via buybacks and dividends. The TSX's leveraged play on WTI/WCS spreads and natural-gas prices.",
        "thesis_zh": "油砂一体化企业与天然气/轻油勘探生产商 — 充沛自由现金流，通过回购与分红回馈。多交所押注 WTI/WCS 价差与天然气价格的杠杆腿。",
        "members": [
            ("CNQ.TO", "Canadian Natural — oil-sands giant"),
            ("SU.TO", "Suncor — integrated oil sands"),
            ("CVE.TO", "Cenovus — integrated"),
            ("IMO.TO", "Imperial Oil"),
            ("TOU.TO", "Tourmaline — gas leader"),
            ("ARX.TO", "ARC Resources"),
            ("WCP.TO", "Whitecap Resources"),
        ],
    },
    "ca_pipelines": {
        "name": "Pipelines & Midstream", "name_zh": "管道与中游",
        "category": "Energy", "category_zh": "能源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The energy-infrastructure toll-takers — pipelines, gas processing and midstream. Long-life, fee-based cash flows and big dividends; a lower-beta, rate-sensitive income complement to the producers.",
        "thesis_zh": "能源基建的'收费站' — 管道、天然气处理与中游。长久期、基于费用的现金流与高分红；相对生产商更低 Beta、对利率敏感的收息补充。",
        "members": [
            ("ENB.TO", "Enbridge — the pipeline giant"),
            ("TRP.TO", "TC Energy"),
            ("PPL.TO", "Pembina Pipeline"),
            ("KEY.TO", "Keyera — gas gathering/processing"),
            ("GEI.TO", "Gibson Energy"),
            ("SOBO.TO", "South Bow — liquids pipelines (TRP spin-off)"),
        ],
    },
    "ca_uranium": {
        "name": "Uranium & Nuclear", "name_zh": "铀与核能",
        "category": "Energy", "category_zh": "能源",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Canada's uranium complex — the dominant producer plus the development names. A high-beta play on the nuclear-renaissance / power-demand thesis and the uranium price; an iconic TSX resource theme.",
        "thesis_zh": "加拿大铀产业链 — 龙头生产商加开发型公司。押注核能复兴/电力需求与铀价的高弹性主题；多交所标志性的资源主题。",
        "members": [
            ("CCO.TO", "Cameco — the uranium major"),
            ("NXE.TO", "NexGen Energy — Rook I development"),
            ("DML.TO", "Denison Mines"),
            ("EFR.TO", "Energy Fuels — uranium + rare earths"),
        ],
    },
    # ───────────────────────────── Materials · 基础材料 ─────────────────────────────
    "ca_base_metals": {
        "name": "Base Metals & Copper", "name_zh": "基本金属与铜",
        "category": "Materials", "category_zh": "基础材料",
        "etf_proxy": "XBM.TO", "etf_proxy_note": "iShares S&P/TSX Base Metals ETF",
        "thesis": "Copper and diversified base-metal miners — leverage to the global growth cycle, electrification demand and supply discipline. The cyclical, China-sensitive end of the TSX materials complex.",
        "thesis_zh": "铜与多元化基本金属矿企 — 受全球增长周期、电气化需求与供给约束驱动。多交所材料板块中周期性、对中国敏感的一端。",
        "members": [
            ("TECK-B.TO", "Teck Resources — copper + coal"),
            ("FM.TO", "First Quantum — copper"),
            ("LUN.TO", "Lundin Mining — base metals"),
            ("IVN.TO", "Ivanhoe Mines — Kamoa-Kakula copper"),
            ("HBM.TO", "Hudbay Minerals"),
            ("CS.TO", "Capstone Copper"),
            ("ERO.TO", "Ero Copper"),
        ],
    },
    "ca_materials": {
        "name": "Fertilizer, Chemicals & Forestry", "name_zh": "化肥化工与林业",
        "category": "Materials", "category_zh": "基础材料",
        "etf_proxy": "XMA.TO", "etf_proxy_note": "iShares S&P/TSX Materials ETF",
        "thesis": "The non-metal materials sleeve — the global potash/nitrogen leader, methanol, lumber and specialty packaging. Levered to crop prices, housing and the industrial cycle.",
        "thesis_zh": "非金属材料板块 — 全球钾肥/氮肥龙头、甲醇、木材与特种包装。受农产品价格、住房与工业周期驱动。",
        "members": [
            ("NTR.TO", "Nutrien — global potash/nitrogen leader"),
            ("MX.TO", "Methanex — the methanol major"),
            ("WFG.TO", "West Fraser Timber — lumber"),
            ("SJ.TO", "Stella-Jones — treated wood"),
            ("CCL-B.TO", "CCL Industries — specialty labels/packaging"),
            ("WPK.TO", "Winpak — packaging"),
        ],
    },
    # ────────────────────────── Industrials & Tech · 工业与科技 ──────────────────────────
    "ca_rails_ind": {
        "name": "Rails & Industrials", "name_zh": "铁路与工业",
        "category": "Industrials & Tech", "category_zh": "工业与科技",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "The transport & industrial backbone — the two transcontinental railways, waste, engineering and equipment names. Steady compounders geared to North American freight, infrastructure and capex.",
        "thesis_zh": "运输与工业骨干 — 两大横贯铁路、固废、工程与设备公司。稳健复利型企业，受北美货运、基建与资本开支驱动。",
        "members": [
            ("CP.TO", "CPKC — the only US-Mexico-Canada railway"),
            ("CNR.TO", "Canadian National Railway"),
            ("WCN.TO", "Waste Connections"),
            ("WSP.TO", "WSP Global — engineering"),
            ("TFII.TO", "TFI International — trucking/logistics"),
            ("TIH.TO", "Toromont — Caterpillar dealer"),
            ("GFL.TO", "GFL Environmental"),
        ],
    },
    "ca_tech": {
        "name": "Technology", "name_zh": "科技",
        "category": "Industrials & Tech", "category_zh": "工业与科技",
        "etf_proxy": "XIT.TO", "etf_proxy_note": "iShares S&P/TSX Capped IT ETF",
        "thesis": "Canada's tech leaders — the e-commerce platform, the serial software acquirer, electronics manufacturing and the SaaS names. The TSX's growth engine, dominated by Shopify and Constellation.",
        "thesis_zh": "加拿大科技龙头 — 电商平台、连环软件并购方、电子制造与 SaaS 公司。多交所的成长引擎，由 Shopify 与 Constellation 主导。",
        "members": [
            ("SHOP.TO", "Shopify — global e-commerce platform"),
            ("CSU.TO", "Constellation Software — serial acquirer"),
            ("CLS.TO", "Celestica — AI-server EMS"),
            ("GIB-A.TO", "CGI — IT services"),
            ("OTEX.TO", "OpenText — enterprise information mgmt"),
            ("DSG.TO", "Descartes Systems — logistics SaaS"),
            ("KXS.TO", "Kinaxis — supply-chain SaaS"),
        ],
    },
    # ─────────────────────── Utilities & Telecom · 公用事业与电信 ───────────────────────
    "ca_utilities": {
        "name": "Utilities & Renewables", "name_zh": "公用事业与可再生能源",
        "category": "Utilities & Telecom", "category_zh": "公用事业与电信",
        "etf_proxy": "XUT.TO", "etf_proxy_note": "iShares S&P/TSX Utilities ETF",
        "thesis": "Regulated power & gas utilities plus the renewable-power developers — long-duration, bond-proxy cash flows and dividend growth. A rate-sensitive defensive anchor with a green-energy growth tail.",
        "thesis_zh": "受监管的电力与燃气公用事业加可再生能源开发商 — 长久期、债券替代型现金流与股息增长。对利率敏感的防御锚，兼具绿色能源成长尾部。",
        "members": [
            ("FTS.TO", "Fortis — regulated utility"),
            ("EMA.TO", "Emera"),
            ("H.TO", "Hydro One — Ontario T&D"),
            ("CU.TO", "Canadian Utilities (ATCO)"),
            ("CPX.TO", "Capital Power"),
            ("BEP-UN.TO", "Brookfield Renewable — global renewables"),
            ("NPI.TO", "Northland Power — offshore wind"),
            ("BLX.TO", "Boralex — wind/solar"),
            ("AQN.TO", "Algonquin Power"),
        ],
    },
    "ca_telecom": {
        "name": "Telecom", "name_zh": "电信",
        "category": "Utilities & Telecom", "category_zh": "公用事业与电信",
        "etf_proxy": "XCD.TO", "etf_proxy_note": "iShares S&P/TSX Communication ETF",
        "thesis": "The Canadian telecom oligopoly — wireless + broadband incumbents with high dividends, now wrestling with price competition and heavy capex. A defensive, rate-sensitive income sleeve.",
        "thesis_zh": "加拿大电信寡头 — 高分红的无线+宽带巨头，正应对价格竞争与高资本开支。防御性、对利率敏感的收息板块。",
        "members": [
            ("BCE.TO", "BCE — Bell Canada"),
            ("T.TO", "Telus"),
            ("RCI-B.TO", "Rogers Communications"),
            ("QBR-B.TO", "Quebecor — Videotron"),
            ("CCA.TO", "Cogeco Communications"),
        ],
    },
    # ──────────────────── Consumer & Real Estate · 消费与地产 ────────────────────
    "ca_consumer": {
        "name": "Consumer Staples & Retail", "name_zh": "必需消费与零售",
        "category": "Consumer & Real Estate", "category_zh": "消费与地产",
        "etf_proxy": "XST.TO", "etf_proxy_note": "iShares S&P/TSX Consumer Staples ETF",
        "thesis": "Defensive consumption — the grocers, the global convenience-store roll-up, the dollar-store and the QSR franchisor. Steady, recession-resilient compounders with pricing power.",
        "thesis_zh": "防御性消费 — 杂货商、全球便利店整合者、一元店与快餐特许经营商。稳健、抗衰退、具提价能力的复利型企业。",
        "members": [
            ("ATD.TO", "Alimentation Couche-Tard — global c-stores"),
            ("L.TO", "Loblaw — #1 grocer"),
            ("MRU.TO", "Metro — grocery/pharmacy"),
            ("DOL.TO", "Dollarama — dollar-store leader"),
            ("QSR.TO", "Restaurant Brands — Tim Hortons/BK/PLK"),
            ("WN.TO", "George Weston — Loblaw parent"),
            ("SAP.TO", "Saputo — dairy processing"),
        ],
    },
    "ca_reits": {
        "name": "REITs", "name_zh": "房地产信托",
        "category": "Consumer & Real Estate", "category_zh": "消费与地产",
        "etf_proxy": "XRE.TO", "etf_proxy_note": "iShares S&P/TSX Capped REIT ETF",
        "thesis": "The Canadian REIT complex — retail, apartment, industrial and diversified landlords. Distribution-yield vehicles highly sensitive to bond yields and the rate cycle; a real-asset income sleeve.",
        "thesis_zh": "加拿大 REIT 板块 — 零售、公寓、工业与多元化地产商。以派息为主、对债券收益率与利率周期高度敏感；实物资产收息板块。",
        "members": [
            ("REI-UN.TO", "RioCan — retail REIT"),
            ("CAR-UN.TO", "Canadian Apartment Properties (CAPREIT)"),
            ("GRT-UN.TO", "Granite — industrial REIT"),
            ("FCR-UN.TO", "First Capital — urban retail"),
            ("CHP-UN.TO", "Choice Properties"),
            ("SRU-UN.TO", "SmartCentres — retail"),
            ("DIR-UN.TO", "Dream Industrial"),
        ],
    },
}

CURATED = "2026-06-18"   # member-expansion pass

# ── 2026-06-18 expansion: on-thesis adds from the canada_search cache. bid -> [(ticker, rationale)];
# validated against the close cache like the base set (fail-loud on a miss).
EXPANSION: dict[str, list[tuple[str, str]]] = {
    "ca_banks": [
        ("GSY.TO", "goeasy — non-prime consumer lender"),
    ],
    "ca_insurers": [
        ("DFY.TO", "Definity Financial — P&C insurer (demutualized)"),
        ("TSU.TO", "Trisura — specialty insurance"),
    ],
    "ca_asset_mgrs": [
        ("BBUC.TO", "Brookfield Business — listed PE / business services"),
    ],
    "ca_gold": [
        ("CG.TO", "Centerra Gold — diversified producer"),
        ("EQX.TO", "Equinox Gold — Americas producer"),
        ("OGC.TO", "OceanaGold"),
        ("TXG.TO", "Torex Gold — Mexico producer"),
        ("WDO.TO", "Wesdome — high-grade Canadian gold"),
        ("DPM.TO", "DPM Metals — low-cost producer + smelting"),
        ("OLA.TO", "Orla Mining — growth producer"),
        ("KNT.TO", "K92 Mining — high-grade PNG"),
    ],
    "ca_silver_royalty": [
        ("EDR.TO", "Endeavour Silver — primary silver producer"),
        ("AYA.TO", "Aya Gold & Silver — Morocco silver"),
        ("SVM.TO", "Silvercorp — China silver/lead/zinc"),
        ("VZLA.TO", "Vizsla Silver — Mexico silver developer"),
        ("DSV.TO", "Discovery Silver — silver/gold developer"),
    ],
    "ca_oil_gas": [
        ("VET.TO", "Vermilion Energy — intl gas + oil"),
        ("BTE.TO", "Baytex Energy — heavy oil + Eagle Ford"),
        ("TVE.TO", "Tamarack Valley — Clearwater oil"),
        ("PEY.TO", "Peyto — low-cost gas"),
        ("AAV.TO", "Advantage Energy — Montney gas"),
        ("BIR.TO", "Birchcliff — Montney gas"),
        ("POU.TO", "Paramount Resources — liquids-rich gas"),
        ("PXT.TO", "Parex Resources — Colombia oil"),
    ],
    "ca_pipelines": [
        ("ALA.TO", "AltaGas — gas distribution + midstream"),
        ("TPZ.TO", "Topaz Energy — royalty + infrastructure"),
        ("SES.TO", "Secure — energy-waste infrastructure"),
    ],
    "ca_base_metals": [
        ("TKO.TO", "Taseko Mines — copper"),
        ("NGEX.TO", "NGEx Minerals — copper-gold developer"),
    ],
    "ca_materials": [
        ("LAC.TO", "Lithium Americas — US lithium (Thacker Pass)"),
        ("VNP.TO", "5N Plus — specialty semiconductor/solar materials"),
        ("LIF.TO", "Labrador Iron Ore Royalty — iron-ore royalty"),
    ],
    "ca_rails_ind": [
        ("BBD-B.TO", "Bombardier — business jets"),
        ("CAE.TO", "CAE — flight simulation & training"),
        ("ATS.TO", "ATS Corp — factory automation"),
        ("STN.TO", "Stantec — engineering / design"),
        ("MDA.TO", "MDA Space — space robotics & satellites"),
        ("FTT.TO", "Finning — Caterpillar dealer"),
        ("RBA.TO", "RB Global — industrial auctions (Ritchie Bros)"),
        ("EIF.TO", "Exchange Income — aviation + manufacturing"),
        ("MG.TO", "Magna International — global auto parts"),
        ("LNR.TO", "Linamar — auto parts + industrial/agri"),
    ],
    "ca_tech": [
        ("BB.TO", "BlackBerry — automotive software (QNX) + cyber"),
        ("LSPD.TO", "Lightspeed Commerce — POS/commerce SaaS"),
        ("TRI.TO", "Thomson Reuters — info-services + AI"),
    ],
    "ca_utilities": [
        ("ACO-X.TO", "ATCO — utilities + structures/logistics"),
        ("BIP-UN.TO", "Brookfield Infrastructure — global infra"),
        ("TA.TO", "TransAlta — power generation"),
        ("SPB.TO", "Superior Plus — propane/energy distribution"),
    ],
    "ca_consumer": [
        ("PBH.TO", "Premium Brands — specialty food manufacturing/distribution"),
        ("MFI.TO", "Maple Leaf Foods — packaged meats"),
        ("EMP-A.TO", "Empire — Sobeys grocery"),
        ("NWC.TO", "North West Company — remote-community retail"),
        ("CTC-A.TO", "Canadian Tire — retail + financial services"),
        ("ATZ.TO", "Aritzia — premium apparel retailer"),
    ],
    "ca_reits": [
        ("BEI-UN.TO", "Boardwalk — apartment REIT"),
        ("IIP-UN.TO", "InterRent — apartment REIT"),
        ("KMP-UN.TO", "Killam — apartment REIT"),
        ("HR-UN.TO", "H&R — diversified REIT"),
        ("CRT-UN.TO", "CT REIT — Canadian Tire-anchored retail"),
        ("AP-UN.TO", "Allied Properties — urban office"),
    ],
}

CONSTRUCTION = ("Equal-weighted, monthly-rebalanced, buy-and-hold between rebalances; dated "
                "membership changes take effect same-day. Benchmark = S&P/TSX Composite (XIC.TO).")
HISTORY_NOTE = ("Series before a basket's creation date are a backtest of the membership as of "
                "creation; live tracking starts at creation. Universe = the canada_search "
                "S&P/TSX Composite cache (~5y).")
NOTE = ("Curated S&P/TSX thematic baskets — hindsight-curated and descriptive, not an "
        "out-of-sample backtest and not a buy list.")


def main() -> int:
    meta = pd.read_parquet(config.data_dir() / "canada_search" / "members.parquet")
    closes = pd.read_parquet(config.data_dir() / "canada_search" / "closes.parquet")
    cols = set(closes.columns)

    def name_of(t: str) -> str:
        if t in meta.index:
            return str(meta.loc[t, "name"])
        return t

    # fold the 2026-06-18 expansion into the base definitions before materialising
    baskets = {k: dict(v) for k, v in BASKETS.items()}
    for bid, adds in EXPANSION.items():
        baskets[bid]["members"] = list(baskets[bid]["members"]) + list(adds)

    out_baskets, missing = {}, []
    for bid, b in baskets.items():
        members = []
        for ticker, rationale in b["members"]:
            if ticker not in cols:
                missing.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name": name_of(ticker), "rationale": rationale})
        cl = [{"date": SEED, "action": "create",
               "note": f"Seeded {b['name']} — equal-weight TSX members."}]
        if bid in EXPANSION:
            cl.append({"date": CURATED, "action": "expand",
                       "note": f"Expanded to {len(members)} members."})
        out_baskets[bid] = {
            "name": b["name"], "name_zh": b["name_zh"],
            "category": b["category"], "category_zh": b["category_zh"],
            "etf_proxy": b["etf_proxy"], "etf_proxy_note": b["etf_proxy_note"],
            "created": SEED, "weighting": "equal",
            "thesis": b["thesis"], "thesis_zh": b["thesis_zh"], "members": members,
            "changelog": cl,
        }

    if missing:
        log.error("TICKERS NOT IN canada_search cache (fix before shipping): %s", ", ".join(missing))
        return 1

    payload = {
        "version": CURATED, "seed_date": SEED, "curated": CURATED,
        "benchmark": "XIC.TO", "benchmark_label": "S&P/TSX", "benchmark_label_zh": "标普/多伦多",
        "construction": CONSTRUCTION, "history_note": HISTORY_NOTE, "note": NOTE,
        "baskets": out_baskets,
    }
    out_dir = config.data_dir() / "baskets_canada"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "membership.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d baskets, %d members, all tickers validated against canada_search",
             out_dir / "membership.json", len(out_baskets), n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
