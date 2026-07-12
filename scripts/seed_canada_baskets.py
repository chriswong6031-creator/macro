"""Seed data/baskets_canada/membership.json — curated S&P/TSX thematic baskets.

The Canada analogue of scripts/seed_china_baskets.py. Defines the recognizable TSX themes —
the Big-Five banks, gold miners, silver & royalty names, oil & gas producers, pipelines,
uranium, base metals, rails, tech, utilities/renewables, telecom, staples/retail and REITs —
and their equal-weight member tickers, then materialises the membership schema
engine.baskets_canada.compute_canada_baskets() consumes.

Member names are filled from data/canada_search/members.parquet and EVERY ticker is validated
against the canada_search close cache (fail loud on a miss) — except tickers in the REMOVED
registry below, which re-encode the nightly reconciler's dated prunes
(scripts/reconcile_membership.py) so a regen reproduces the live file. Benchmark = S&P/TSX Composite
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
        "thesis": "Canada's major banks and alternative lenders. Tracks credit, mortgages, rates and the TSX financials core.",
        "thesis_zh": "加拿大主要银行和替代贷款机构。跟踪信贷、房贷、利率和 TSX 金融核心。",
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
        "thesis": "Life and P&C insurers geared to equity markets, yields and book value.",
        "thesis_zh": "寿险和财险公司，受股市、利率和账面价值影响。",
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
        "thesis": "Brookfield, Power, Onex, fund managers and the exchange. Tracks fee capital, deals and private markets.",
        "thesis_zh": "Brookfield、Power、Onex、基金管理人和交易所。跟踪收费资本、交易和私募市场。",
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
        "thesis": "Senior and mid-tier gold miners. High operating leverage to bullion, real rates and central-bank demand.",
        "thesis_zh": "大型和中型金矿商。对金价、实际利率和央行需求具有高杠杆。",
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
        "thesis": "Silver producers plus royalty and streaming names. Precious-metals beta with mixed operating risk.",
        "thesis_zh": "白银生产商以及 royalty/streaming 公司。贵金属贝塔与运营风险并存。",
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
        "thesis": "Oil sands, gas and light-oil producers. Tracks WTI/WCS spreads, natural gas and cash-return discipline.",
        "thesis_zh": "油砂、天然气和轻质油生产商。跟踪 WTI/WCS 价差、天然气和现金回报纪律。",
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
        "thesis": "Pipelines and midstream toll-takers with fee-based cash flow, dividends and rate sensitivity.",
        "thesis_zh": "管道和中游收费型资产，具有稳定现金流、股息和利率敏感性。",
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
        "thesis": "Canada's uranium producer and developers. High-beta read on nuclear demand and uranium prices.",
        "thesis_zh": "加拿大铀生产商和开发商。高贝塔反映核能需求和铀价。",
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
        "thesis": "Copper and base-metal miners tied to global growth, electrification and China demand.",
        "thesis_zh": "铜和基本金属矿商，受全球增长、电气化和中国需求影响。",
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
        "thesis": "Potash, chemicals, lumber and specialty packaging tied to crops, housing and industrial demand.",
        "thesis_zh": "钾肥、化工、木材和特种包装，受农业、住房和工业需求影响。",
        "members": [
            ("NTR.TO", "Nutrien — global potash/nitrogen leader"),
            ("MX.TO", "Methanex — the methanol major"),
            ("WFG.TO", "West Fraser Timber — lumber"),
            ("SJ.TO", "Stella-Jones — treated wood"),
            ("CCL-B.TO", "CCL Industries — specialty labels/packaging"),
            ("WPK.TO", "Winpak — packaging"),   # removed 2026-07-01 — see REMOVED
        ],
    },
    # ────────────────────────── Industrials & Tech · 工业与科技 ──────────────────────────
    "ca_rails_ind": {
        "name": "Rails & Industrials", "name_zh": "铁路与工业",
        "category": "Industrials & Tech", "category_zh": "工业与科技",
        "etf_proxy": None, "etf_proxy_note": "",
        "thesis": "Rails, waste, engineering and equipment names. Tracks freight, infrastructure and capex.",
        "thesis_zh": "铁路、废弃物处理、工程和设备公司。跟踪货运、基建和资本开支。",
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
        "thesis": "Shopify, Constellation, electronics and SaaS names. Canada's large-cap growth sleeve.",
        "thesis_zh": "Shopify、Constellation、电子和 SaaS 公司。加拿大大盘成长股代表。",
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
        "thesis": "Regulated utilities and renewable-power developers. Defensive, rate-sensitive cash flows.",
        "thesis_zh": "受监管公用事业和可再生电力开发商。防御性现金流，受利率影响。",
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
        "thesis": "Wireless and broadband incumbents. Defensive income sleeve facing competition and capex pressure.",
        "thesis_zh": "无线和宽带龙头。防御性收入板块，但面临竞争和资本开支压力。",
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
        "thesis": "Grocers, convenience, dollar-store and QSR leaders. Defensive read on Canadian consumption.",
        "thesis_zh": "食品零售、便利店、折扣店和快餐龙头。防御性观察加拿大消费。",
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
        "thesis": "Retail, apartment, industrial and diversified REITs. Real-asset income tied to yields and rates.",
        "thesis_zh": "零售、公寓、工业和综合 REIT。实物资产收入受收益率和利率影响。",
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
        ("GSY.TO", "goeasy — non-prime consumer lender"),   # removed 2026-07-01 — see REMOVED
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

# ── Post-seed removals (COPY SYNC with the live membership.json) ────────────────────────
# The nightly membership↔cache reconciler (scripts/reconcile_membership.py, end-of-collect
# gate) prunes members whose ticker drops off the canada_search close cache, appending a
# dated changelog entry to the LIVE file. Those removals are re-encoded here so a wholesale
# regen reproduces the live file instead of resurrecting the member or failing the cache
# check. The member's tuple STAYS in BASKETS/EXPANSION above (it feeds the historical count
# in the expand note); the (basket_id, ticker) key here excludes it from the emitted members
# and appends the exact changelog row. Notes are verbatim from the live file — don't reword.
# Both names still trade on the TSX; they were deleted from the S&P/TSX Composite at the
# 2026-06-22 quarterly review (goeasy after the LendCare bad-loan crash; Winpak on float),
# and canada_search's universe IS the Composite (XIC holdings) — genuine index churn.
REMOVED: dict[tuple[str, str], dict] = {
    ("ca_banks", "GSY.TO"): {
        "date": "2026-07-01",
        "note": "GSY.TO: removed after leaving the price cache.",
    },
    ("ca_materials", "WPK.TO"): {
        "date": "2026-07-01",
        "note": "WPK.TO: removed after leaving the price cache.",
    },
}

CONSTRUCTION = ("Equal-weight baskets, rebalanced monthly, measured against the S&P/TSX "
                "Composite.")
HISTORY_NOTE = ("Available history comes from the canada_search cache. Pre-launch series use "
                "the basket's starting membership.")
NOTE = ("Curated S&P/TSX theme baskets for monitoring rotation. Descriptive only, not a "
        "buy list.")


def main() -> int:
    meta = pd.read_parquet(config.data_dir() / "canada_search" / "members.parquet")
    closes = pd.read_parquet(config.data_dir() / "canada_search" / "closes.parquet")
    cols = set(closes.columns)
    out_dir = config.data_dir() / "baskets_canada"

    # Names already in the LIVE membership file — fallback when a member's meta row is
    # missing (a bare ticker must never overwrite a good name). Cache names win when
    # present: corporate renames (e.g. Taseko → Trekor Metals, 2026-06-29) flow through.
    live_names: dict[tuple[str, str], str] = {}
    live_p = out_dir / "membership.json"
    if live_p.exists():
        try:
            live_doc = json.loads(live_p.read_text())
            live_names = {(bid, m["ticker"]): m["name"]
                          for bid, b in live_doc.get("baskets", {}).items()
                          for m in b.get("members", []) if m.get("name")}
        except Exception as e:  # noqa: BLE001 — degraded live file just loses the fallback
            log.warning("live membership.json unreadable (%s) — no name fallback", e)

    def name_of(bid: str, t: str) -> str:
        if t in meta.index:
            return str(meta.loc[t, "name"])
        return live_names.get((bid, t)) or t

    # fold the 2026-06-18 expansion into the base definitions before materialising
    baskets = {k: dict(v) for k, v in BASKETS.items()}
    for bid, adds in EXPANSION.items():
        baskets[bid]["members"] = list(baskets[bid]["members"]) + list(adds)

    out_baskets, missing = {}, []
    for bid, b in baskets.items():
        members, removals = [], []
        for ticker, rationale in b["members"]:
            rm = REMOVED.get((bid, ticker))
            if rm is not None:
                if ticker in cols:
                    log.warning("removed member %s:%s is back on the canada_search cache — "
                                "consider re-adding it with a dated changelog entry", bid, ticker)
                removals.append(rm)
                continue
            if ticker not in cols:
                missing.append(f"{bid}:{ticker}")
                continue
            members.append({"ticker": ticker, "added": SEED, "removed": None,
                            "name": name_of(bid, ticker), "rationale": rationale})
        cl = [{"date": SEED, "action": "create",
               "note": f"Seeded {b['name']} — equal-weight TSX members."}]
        if bid in EXPANSION:
            # count at expansion date, before later removals
            cl.append({"date": CURATED, "action": "expand",
                       "note": f"Expanded to {len(members) + len(removals)} members."})
        cl += [{"date": rm["date"], "action": "remove", "note": rm["note"]} for rm in removals]
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
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "membership.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d baskets, %d members, all tickers validated against canada_search",
             out_dir / "membership.json", len(out_baskets), n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
