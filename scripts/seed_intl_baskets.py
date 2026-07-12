"""Seed data/baskets_intl/membership.json — curated CROSS-COUNTRY international thematic baskets.

The international (developed ex-US + India) analogue of scripts/seed_canada_baskets.py, but
built for a multi-country universe: the baskets are GLOBAL sector themes that deliberately mix
equities across Japan, the UK, Europe, India, Korea, Taiwan and Australia (e.g. Global
Semiconductors = TSMC + Samsung + ASML + Tokyo Electron…), plus a handful of single-country
structural-growth sleeves (Japan Inc., India Growth, Korea Tech).

Selection is DETERMINISTIC and grounded: each theme is a rule over the real
data/intl_search/members.parquet universe (GICS sector ∩ name-keyword ∩ optional country),
ranked by index weight and capped — every emitted ticker exists in the universe AND in the
intl_search close cache (fail-loud on a miss). No hand-typed ticker can be hallucinated; the
seeder only ever picks names that are actually in the cache. Run with `--dry` to print each
theme's matched members for review; run plain to materialise the membership schema that
engine.baskets_intl.compute_intl_baskets() consumes.

Benchmark = a cap-weighted composite of the universe ("Intl ex-US composite", ticker _INTLC),
built by engine.baskets_intl.

BOOTSTRAP-ONLY: once data/baskets_intl/membership.json exists, the LIVE file is the ledger of
record — it accrues history this seeder cannot reproduce (dated changelog rows such as the
2026-07-01 MONC.MI prune, now applied automatically by scripts/reconcile_membership.py at the
end-of-collect gate), and rank-by-weight selection over a refreshed universe reshuffles the
picks anyway. Re-running therefore REFUSES to overwrite an existing membership.json unless
--force is passed; ongoing membership changes belong on the live file as dated edits (nightly
is the sole advancer of forward ledgers).

HONEST BY CONSTRUCTION: membership is curated today with knowledge of the period, so the ~5y
series is HINDSIGHT-curated and descriptive — not an out-of-sample backtest, not a buy list.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_intl_baskets")

SEED = "2021-06-15"      # start of the intl_search close cache
CURATED = "2026-06-19"

# Each theme: a rule over data/intl_search/members.parquet. `sectors` = GICS sectors to draw
# from; `include`/`exclude` = case-insensitive regex on the company name; `countries` = optional
# ISO filter; `cap` = keep the top-N by index weight; `anchors` = tickers force-kept even if the
# name regex misses them (still validated against the cache). Flags (🇯🇵 etc.) ride in the
# member rationale so the cross-country mix is legible on the page.
THEMES: list[dict] = [
    # ───────────────────────── Technology ─────────────────────────
    {
        "id": "intl_semis", "name": "Global Semiconductors", "name_zh": "全球半导体",
        "category": "Technology", "category_zh": "科技",
        "thesis": "The non-US foundries, memory makers, chip-equipment and fabless leaders that sit at the centre of the AI build-out — TSMC and the Taiwan complex, Samsung and SK Hynix in Korea, Tokyo Electron / Advantest / Disco in Japan and ASML / Infineon in Europe. The single most important cross-country tech theme.",
        "thesis_zh": "AI 建设核心的非美晶圆代工、存储、设备与无晶圆厂龙头 — 台积电与台湾产业链、韩国三星与 SK 海力士、日本东京威力科创/爱德万/迪斯科，以及欧洲 ASML 与英飞凌。最重要的跨国科技主题。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"semiconduct|tsmc|taiwan semi|hynix|mediatek|tokyo electron|advantest|disco|renesas|infineon|stmicro|united micro|umc|ase tech|ase technology|realtek|global unichip|novatek|himax|silergy|nanya|winbond|macronix|powerchip|vanguard intl|alchip|egis|parade|nuvoton|asml|be semi|nordic semi|soitec",
                 "exclude": r"materials? ltd|chemical", "cap": 18,
                 "anchors": ["2330.TW", "005930.KS", "000660.KS", "ASML.AS", "8035.T", "6857.T", "6146.T", "2454.TW", "IFX.DE"]},
    },
    {
        "id": "intl_tech_hw", "name": "Tech Hardware & Components", "name_zh": "科技硬件与零部件",
        "category": "Technology", "category_zh": "科技",
        "thesis": "The picks-and-shovels of global electronics — contract manufacturers, passive components, connectors, optics and precision parts that build the devices and AI servers. Foxconn, Murata, TDK, Quanta, Wistron and the component makers across Taiwan and Japan.",
        "thesis_zh": "全球电子的“卖铲人” — 制造代工、被动元件、连接器、光学与精密零件，组装设备与 AI 服务器。鸿海、村田、TDK、广达、纬创及台日零部件厂。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"hon hai|foxconn|murata|tdk|quanta|wistron|kyocera|largan|yageo|delta electronics|lite on|ibiden|unimicron|zhen ding|accton|wiwynn|king slide|chroma|asia vital|gold circuit|elite material|nidec|hirose|alps|taiyo yuden|japan aviation|fujitsu|nec corp|asustek|micro star|gigabyte|innolux|au optronics",
                 "exclude": r"semiconduct", "cap": 16},
    },
    {
        "id": "intl_software", "name": "Software & IT Services", "name_zh": "软件与IT服务",
        "category": "Technology", "category_zh": "科技",
        "thesis": "The global enterprise-software and IT-services leaders outside the US — Europe's SAP and Capgemini, India's outsourcing giants (Infosys, TCS, HCL, Wipro), and the UK / Australia SaaS names. Levered to the digitisation and AI-services cycle.",
        "thesis_zh": "非美的企业软件与 IT 服务龙头 — 欧洲 SAP 与凯捷、印度外包巨头（Infosys、TCS、HCL、Wipro），以及英澳 SaaS 公司。受益于数字化与 AI 服务周期。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"\bsap\b|infosys|tata consult|hcl tech|wipro|tech mahindra|ltimindtree|persistent|coforge|mphasis|dassault|nemetschek|amadeus|sage group|softcat|computacenter|xero|wisetech|technology one|capgemini|atos|teamviewer|temenos|nice ltd",
                 "cap": 16},
    },
    # ───────────────────────── Financials ─────────────────────────
    {
        "id": "intl_banks", "name": "Global Banks", "name_zh": "全球银行",
        "category": "Financials", "category_zh": "金融",
        "thesis": "The big non-US money-centre and retail banks — Japan's megabanks (MUFG, SMFG, Mizuho), the UK lenders (HSBC, Barclays, Lloyds, NatWest), Europe's Santander, India's private banks (HDFC, ICICI, Axis, Kotak, SBI), Korea's financial groups and the Australian majors. A direct read on global credit and rates.",
        "thesis_zh": "非美的大型商业与零售银行 — 日本三大行（三菱日联、三井住友、瑞穗）、英国（汇丰、巴克莱、劳埃德、NatWest）、欧洲桑坦德、印度私行（HDFC、ICICI、Axis、Kotak、SBI）、韩国金融集团与澳洲四大行。直接反映全球信贷与利率。",
        "rule": {"sectors": ["Financials"],
                 "include": r"\bbank|banking|financial group|financial holding|mitsubishi ufj|sumitomo mitsui|mizuho",
                 "exclude": r"insurance|life|reinsur|asset manage|exchange|invest manage|securit", "cap": 20,
                 "anchors": ["8306.T", "8316.T", "8411.T", "HSBA.L", "BARC.L", "SAN.MC"]},
    },
    {
        "id": "intl_insurers", "name": "Insurers & Diversified Financials", "name_zh": "保险与多元金融",
        "category": "Financials", "category_zh": "金融",
        "thesis": "The global insurance and diversified-financial complex — European insurers (Allianz, Zurich), the UK life and P&C names (Prudential, Aviva), Japan's Tokio Marine and MS&AD, Korea's Samsung Life, the exchanges (LSE) and the Australian insurers. Long-bond-yield and equity-market geared book value.",
        "thesis_zh": "全球保险与多元金融 — 欧洲保险（安联、苏黎世）、英国寿险与财险（保诚、Aviva）、日本东京海上与 MS&AD、韩国三星生命、交易所（伦交所）与澳洲险企。账面价值与长债收益率及权益市场挂钩。",
        "rule": {"sectors": ["Financials"],
                 "include": r"insurance|life ltd|reinsur|assicurazioni|allianz|\baxa\b|generali|aviva|prudential|legal & general|admiral|tokio marine|samsung life|samsung fire|qbe|suncorp|medibank|sompo|dai.ichi|t&d holdings|hiscox|beazley|phoenix group|st james|m&g|aberdeen|schroders|amundi|deutsche boerse|london stock exchange|macquarie|zurich|ms&ad|3i group",
                 "exclude": r"trust plc|investment trust", "cap": 16},
    },
    # ───────────────────────── Healthcare ─────────────────────────
    {
        "id": "intl_pharma", "name": "Global Pharma & Healthcare", "name_zh": "全球制药与医疗",
        "category": "Healthcare", "category_zh": "医疗保健",
        "thesis": "The non-US drug majors and healthcare leaders — AstraZeneca and GSK in the UK, Roche / Novartis / Sanofi in Europe, Japan's Takeda / Chugai / Otsuka, India's Sun Pharma and the hospital chains, and Australia's CSL. Defensive growth with global drug pipelines.",
        "thesis_zh": "非美的制药巨头与医疗龙头 — 英国阿斯利康与 GSK、欧洲罗氏/诺华/赛诺菲、日本武田/中外/大塚、印度太阳制药与医院连锁，以及澳洲 CSL。具全球药物管线的防御性成长。",
        "rule": {"sectors": ["Health Care"], "cap": 18},
    },
    # ───────────────────────── Industrials ─────────────────────────
    {
        "id": "intl_defense", "name": "Defense & Aerospace", "name_zh": "国防与航空航天",
        "category": "Industrials", "category_zh": "工业",
        "thesis": "The global re-armament trade outside the US — Europe's BAE Systems, Rheinmetall, Thales, Saab, Safran, Airbus and Rolls-Royce, plus Japan's heavy-industry primes (Mitsubishi Heavy, Kawasaki, IHI) and Korea's defense exporters (Hanwha Aerospace, Korea Aerospace). Levered to rising NATO and Asian defense budgets.",
        "thesis_zh": "非美的全球再武装交易 — 欧洲 BAE、莱茵金属、泰雷兹、绅宝、赛峰、空客与罗罗，加日本重工三巨头（三菱重工、川崎重工、IHI）与韩国国防出口商（韩华航空、韩国航空）。受益于北约与亚洲国防预算上升。",
        "rule": {"sectors": ["Industrials"],
                 "include": r"bae system|rheinmetall|thales|leonardo|saab|rolls.?royce|safran|airbus|babcock|qinetiq|chemring|hensoldt|kongsberg|dassault aviation|mitsubishi heavy|kawasaki heavy|\bihi\b|hanwha aero|hyundai rotem|korea aero|hanwha system",
                 "cap": 14, "anchors": ["BA.L", "RHM.DE", "RR.L", "7011.T"]},
    },
    {
        "id": "intl_automation", "name": "Industrial Automation & Machinery", "name_zh": "工业自动化与机械",
        "category": "Industrials", "category_zh": "工业",
        "thesis": "The global factory-automation and capital-goods leaders — Europe's Siemens, Schneider, ABB, Sandvik and Legrand, and Japan's robotics and motion champions (Fanuc, Daikin, SMC, Mitsubishi Electric, Nidec). The capex-cycle and re-shoring beneficiaries.",
        "thesis_zh": "全球工厂自动化与资本品龙头 — 欧洲西门子、施耐德、ABB、山特维克与罗格朗，日本机器人与运动控制冠军（发那科、大金、SMC、三菱电机、日本电产）。资本开支周期与回流受益者。",
        "rule": {"sectors": ["Industrials"],
                 "include": r"siemens|schneider|\babb\b|atlas copco|legrand|sandvik|alfa laval|kone|epiroc|spectris|smiths group|fanuc|smc corp|daikin|nidec|yaskawa|misumi|nabtesco|hitachi|mitsubishi electric|omron|smc\b|halma|spirax|rotork|renishaw|schindler|\bgea\b|kion",
                 "exclude": r"heavy|defense", "cap": 16},
    },
    # ───────────────────────── Consumer ─────────────────────────
    {
        "id": "intl_autos", "name": "Autos & Mobility", "name_zh": "汽车与出行",
        "category": "Consumer", "category_zh": "消费",
        "thesis": "The world's car makers and their suppliers outside the US — Toyota, Honda and the Japanese OEMs, Germany's Mercedes / BMW / VW, Korea's Hyundai and Kia, India's Tata Motors and Maruti, plus the big parts makers (Denso, Bridgestone). A cyclical, EV-transition and global-demand play.",
        "thesis_zh": "非美的全球车企及供应商 — 丰田、本田与日系车厂、德国奔驰/宝马/大众、韩国现代与起亚、印度塔塔汽车与马鲁蒂铃木，加大型零部件厂（电装、普利司通）。周期性、电动化转型与全球需求主题。",
        "rule": {"sectors": ["Consumer Discretionary"],
                 "include": r"toyota|honda|nissan|suzuki|mazda|subaru|mercedes|\bbmw\b|volkswagen|porsche|stellantis|renault|hyundai motor|\bkia\b|tata motors|maruti|mahindra & mahindra|bajaj auto|eicher|denso|bridgestone|continental ag|aisin|toyota industries|valeo|forvia|pirelli",
                 "exclude": r"hotel", "cap": 16,
                 "anchors": ["7203.T", "7267.T", "MBG.DE", "BMW.DE", "VOW3.DE"]},
    },
    {
        "id": "intl_luxury", "name": "Luxury & Premium Brands", "name_zh": "奢侈品与高端品牌",
        "category": "Consumer", "category_zh": "消费",
        "thesis": "Europe's incomparable luxury houses plus the global premium spirits and apparel leaders — LVMH, Hermès, Richemont, L'Oréal, Kering, Ferrari, Adidas, Burberry, Pernod Ricard and Diageo. Pricing power, global aspirational demand and a China-consumer beta.",
        "thesis_zh": "欧洲无可比拟的奢侈品集团加全球高端烈酒与服饰龙头 — LVMH、爱马仕、历峰、欧莱雅、开云、法拉利、阿迪达斯、博柏利、保乐力加与帝亚吉欧。定价权、全球向往型需求与中国消费 Beta。",
        "rule": {"sectors": ["Consumer Discretionary", "Consumer Staples"],
                 "include": r"lvmh|hermes|christian dior|kering|moncler|ferrari|adidas|\bpuma\b|burberry|brunello|prada|essilor|salvatore|richemont|swatch|pernod|diageo|remy|campari|davide campari|l'?oreal",
                 "cap": 16, "anchors": ["MC.PA", "RMS.PA", "OR.PA", "ADS.DE", "DGE.L"]},
    },
    # ───────────────────────── Energy & Materials ─────────────────────────
    {
        "id": "intl_energy", "name": "Global Energy", "name_zh": "全球能源",
        "category": "Energy & Materials", "category_zh": "能源与材料",
        "thesis": "The non-US integrated oil & gas majors and producers — Shell, BP and TotalEnergies, Italy's Eni, Australia's Woodside and Santos, India's Reliance and ONGC, and Japan's Inpex and Eneos. Levered to crude, LNG and the global energy cycle.",
        "thesis_zh": "非美的一体化油气巨头与生产商 — 壳牌、BP 与道达尔、意大利埃尼、澳洲伍德赛德与桑托斯、印度信实与 ONGC，以及日本国际石油与 ENEOS。受原油、LNG 与全球能源周期驱动。",
        "rule": {"sectors": ["Energy"], "cap": 14},
    },
    {
        "id": "intl_mining", "name": "Mining & Metals", "name_zh": "矿业与金属",
        "category": "Energy & Materials", "category_zh": "能源与材料",
        "thesis": "The world's diversified miners and steelmakers ex-US — BHP, Rio Tinto, Glencore, Anglo American, Antofagasta and Fortescue, plus Korea's POSCO and India's Tata Steel / JSW / Vedanta. The cyclical, electrification-and-China-demand metals complex.",
        "thesis_zh": "非美的全球多元化矿企与钢铁商 — 必和必拓、力拓、嘉能可、英美资源、安托法加斯塔与 Fortescue，加韩国 POSCO 与印度塔塔钢铁/JSW/韦丹塔。周期性、受电气化与中国需求驱动的金属板块。",
        "rule": {"sectors": ["Materials"],
                 "include": r"\bbhp\b|rio tinto|glencore|anglo american|antofagasta|fortescue|\bvale\b|posco|arcelor|tata steel|\bjsw\b|hindalco|vedanta|south32|mineral resources|boliden|\bnmdc\b|nippon steel|jfe|sumitomo metal|korea zinc|teck",
                 "cap": 16, "anchors": ["BHP.AX", "RIO.L", "GLEN.L", "AAL.L", "FMG.AX"]},
    },
    # ───────────────────────── Communication ─────────────────────────
    {
        "id": "intl_telecom", "name": "Telecom, Media & Internet", "name_zh": "电信媒体与互联网",
        "category": "Communication", "category_zh": "通信",
        "thesis": "The global communication leaders outside the US — Japan's SoftBank, NTT, KDDI and Nintendo, Europe's Deutsche Telekom and Vodafone, Korea's internet platform Naver, India's Bharti Airtel and the UK media names. A mix of defensive carriers and Asian-internet / media growth.",
        "thesis_zh": "非美的全球通信龙头 — 日本软银、NTT、KDDI 与任天堂、欧洲德国电信与沃达丰、韩国互联网平台 Naver、印度 Bharti Airtel 与英国媒体股。防御性运营商与亚洲互联网/媒体成长的混合。",
        "rule": {"sectors": ["Communication"], "cap": 16},
    },
    # ───────────────────────── Regional structural-growth sleeves ─────────────────────────
    {
        "id": "intl_india", "name": "India Growth", "name_zh": "印度成长",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "The blue-chip face of India's structural-growth story — Reliance, the private banks (HDFC, ICICI), the IT-services majors (Infosys, TCS), Bharti Airtel and the industrial and consumer leaders. The highest-growth large-cap market in the universe.",
        "thesis_zh": "印度结构性成长故事的蓝筹代表 — 信实、私营银行（HDFC、ICICI）、IT 服务巨头（Infosys、TCS）、Bharti Airtel 与工业消费龙头。本组合中成长最快的大盘市场。",
        "rule": {"countries": ["IN"], "cap": 18},
    },
    {
        "id": "intl_japan", "name": "Japan Inc.", "name_zh": "日本企业",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "The large-cap heart of the Japan reflation and corporate-reform trade — the megabanks, trading houses, Toyota and the global tech and industrial champions. Geared to the end of deflation, a weak yen and improving capital returns.",
        "thesis_zh": "日本再通胀与公司治理改革交易的大盘核心 — 三大行、综合商社、丰田与全球科技工业冠军。受益于通缩终结、日元偏弱与资本回报改善。",
        "rule": {"countries": ["JP"], "cap": 18},
    },
    {
        "id": "intl_korea", "name": "Korea Tech & Industry", "name_zh": "韩国科技与工业",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "Korea's export champions and the 'Value-Up' re-rating story — Samsung Electronics and SK Hynix in memory, the internet platforms, Hyundai and the battery / shipbuilding / defense names. A high-beta read on global tech and trade.",
        "thesis_zh": "韩国出口冠军与“企业价值提升”重估故事 — 存储的三星电子与 SK 海力士、互联网平台、现代汽车以及电池/造船/国防股。对全球科技与贸易的高 Beta 读数。",
        "rule": {"countries": ["KR"], "cap": 16},
    },
    {
        "id": "intl_uk", "name": "UK Blue Chips", "name_zh": "英国蓝筹",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "The FTSE 100 large-cap core — the global-facing UK leaders in energy, pharma, banks, consumer staples and miners (Shell, AstraZeneca, HSBC, Unilever, BP, Rio Tinto). A cheap, dividend-rich, internationally-earning equity sleeve.",
        "thesis_zh": "富时 100 大盘核心 — 面向全球的英国能源、制药、银行、必需消费与矿业龙头（壳牌、阿斯利康、汇丰、联合利华、BP、力拓）。低估值、高股息、收入来自全球的权益板块。",
        "rule": {"countries": ["GB"], "cap": 18},
    },
]

# Flag emoji per ISO so the page legibly shows the cross-country mix in each member rationale.
FLAG = {"JP": "🇯🇵", "GB": "🇬🇧", "IN": "🇮🇳", "EZ": "🇪🇺", "KR": "🇰🇷", "TW": "🇹🇼", "AU": "🇦🇺"}

CONSTRUCTION = ("Equal-weighted, monthly-rebalanced, buy-and-hold between rebalances; dated "
                "membership changes take effect same-day. Each theme is a deterministic rule "
                "(GICS sector ∩ name ∩ country, ranked by index weight) over the intl_search "
                "universe, so every member is a real, cache-validated ticker. Benchmark = a "
                "cap-weighted composite of the universe (Intl ex-US composite).")
HISTORY_NOTE = ("Series before a basket's creation date are a backtest of the membership as of "
                "creation; live tracking starts at creation. Universe = the intl_search cache "
                "(developed ex-US + India large-caps across JP/GB/EU/IN/KR/TW/AU, ~5y).")
NOTE = ("Curated international (ex-US) thematic baskets that deliberately mix equities across "
        "countries — hindsight-curated and descriptive, not an out-of-sample backtest and not a "
        "buy list.")


def _select(rule: dict, m: pd.DataFrame, cols: set) -> list[str]:
    df = m
    if rule.get("sectors"):
        df = df[df["sector"].isin(rule["sectors"])]
    if rule.get("countries"):
        df = df[df["country"].isin(rule["countries"])]
    if rule.get("include"):
        df = df[df["name"].str.contains(rule["include"], case=False, regex=True, na=False)]
    if rule.get("exclude"):
        df = df[~df["name"].str.contains(rule["exclude"], case=False, regex=True, na=False)]
    df = df.sort_values("weight", ascending=False)
    if rule.get("cap"):
        df = df.head(rule["cap"])
    picked = [t for t in df.index if t in cols]
    for a in rule.get("anchors", []):       # force-keep the recognisable anchors (validated)
        if a in cols and a not in picked:
            picked.append(a)
    return picked


def main() -> int:
    dry = "--dry" in sys.argv
    force = "--force" in sys.argv
    out_path = config.data_dir() / "baskets_intl" / "membership.json"
    if out_path.exists() and not dry and not force:
        log.error("refusing to overwrite %s — the live file is the ledger of record (dated "
                  "changelog/member history this seeder cannot reproduce, and a re-run "
                  "reshuffles the rank-by-weight selection). Make dated edits to the live "
                  "file instead, or pass --force to re-bootstrap from scratch.", out_path)
        return 1
    m = pd.read_parquet(config.data_dir() / "intl_search" / "members.parquet")
    closes = pd.read_parquet(config.data_dir() / "intl_search" / "closes.parquet")
    cols = set(closes.columns)

    out_baskets, total = {}, 0
    for spec in THEMES:
        tickers = _select(spec["rule"], m, cols)
        if len(tickers) < 3:
            log.error("theme %s has only %d members — widen the rule", spec["id"], len(tickers))
            return 1
        members = []
        for t in tickers:
            row = m.loc[t]
            cc = str(row["country"])
            members.append({"ticker": t, "added": SEED, "removed": None,
                            "name": str(row["name"]),
                            "rationale": f"{FLAG.get(cc, '')} {cc} · {row['name']}".strip()})
        total += len(members)
        if dry:
            log.info("[%s] %s — %d members", spec["id"], spec["name"], len(members))
            for mm in members:
                log.info("    %-12s %s", mm["ticker"], mm["rationale"])
            continue
        out_baskets[spec["id"]] = {
            "name": spec["name"], "name_zh": spec.get("name_zh", spec["name"]),
            "category": spec["category"], "category_zh": spec.get("category_zh", spec["category"]),
            "etf_proxy": None, "etf_proxy_note": "",
            "created": SEED, "weighting": "equal",
            "thesis": spec["thesis"], "thesis_zh": spec.get("thesis_zh", spec["thesis"]),
            "members": members,
            "changelog": [{"date": SEED, "action": "create",
                           "note": f"Seeded {spec['name']} — equal-weight cross-country members."}],
        }

    if dry:
        log.info("DRY RUN — %d themes, %d members total (nothing written)", len(THEMES), total)
        return 0

    payload = {
        "version": CURATED, "seed_date": SEED, "curated": CURATED,
        "benchmark": "_INTLC", "benchmark_label": "Intl ex-US", "benchmark_label_zh": "国际(除美)",
        "construction": CONSTRUCTION, "history_note": HISTORY_NOTE, "note": NOTE,
        "baskets": out_baskets,
    }
    out_dir = config.data_dir() / "baskets_intl"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "membership.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.info("wrote %s — %d baskets, %d members, all tickers validated against intl_search",
             out_dir / "membership.json", len(out_baskets), total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
