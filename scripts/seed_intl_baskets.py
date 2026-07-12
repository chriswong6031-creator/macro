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
# COPY SYNC: name/thesis/*_zh here and CONSTRUCTION/HISTORY_NOTE/NOTE below must match the
# live data/baskets_intl/membership.json — this seeder regenerates it WHOLESALE, so copy edits
# made directly to the live file are clobbered on the next run unless mirrored here.
THEMES: list[dict] = [
    # ───────────────────────── Technology ─────────────────────────
    {
        "id": "intl_semis", "name": "Global Semiconductors", "name_zh": "全球半导体",
        "category": "Technology", "category_zh": "科技",
        "thesis": "Non-US chip leaders across foundry, memory, equipment and fabless. A clean read on the global AI hardware cycle.",
        "thesis_zh": "覆盖晶圆代工、存储、设备与无晶圆厂的非美芯片龙头。用于观察全球 AI 硬件周期。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"semiconduct|tsmc|taiwan semi|hynix|mediatek|tokyo electron|advantest|disco|renesas|infineon|stmicro|united micro|umc|ase tech|ase technology|realtek|global unichip|novatek|himax|silergy|nanya|winbond|macronix|powerchip|vanguard intl|alchip|egis|parade|nuvoton|asml|be semi|nordic semi|soitec",
                 "exclude": r"materials? ltd|chemical", "cap": 18,
                 "anchors": ["2330.TW", "005930.KS", "000660.KS", "ASML.AS", "8035.T", "6857.T", "6146.T", "2454.TW", "IFX.DE"]},
    },
    {
        "id": "intl_tech_hw", "name": "Tech Hardware & Components", "name_zh": "科技硬件与零部件",
        "category": "Technology", "category_zh": "科技",
        "thesis": "Electronics manufacturers and component suppliers that build devices, networks and AI servers.",
        "thesis_zh": "制造设备、网络硬件与 AI 服务器的电子代工和零部件供应商。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"hon hai|foxconn|murata|tdk|quanta|wistron|kyocera|largan|yageo|delta electronics|lite on|ibiden|unimicron|zhen ding|accton|wiwynn|king slide|chroma|asia vital|gold circuit|elite material|nidec|hirose|alps|taiyo yuden|japan aviation|fujitsu|nec corp|asustek|micro star|gigabyte|innolux|au optronics",
                 "exclude": r"semiconduct", "cap": 16},
    },
    {
        "id": "intl_software", "name": "Software & IT Services", "name_zh": "软件与IT服务",
        "category": "Technology", "category_zh": "科技",
        "thesis": "Non-US enterprise software, IT services and SaaS names tied to digitization and AI services demand.",
        "thesis_zh": "非美企业软件、IT 服务与 SaaS 公司，受数字化和 AI 服务需求驱动。",
        "rule": {"sectors": ["Information Technology"],
                 "include": r"\bsap\b|infosys|tata consult|hcl tech|wipro|tech mahindra|ltimindtree|persistent|coforge|mphasis|dassault|nemetschek|amadeus|sage group|softcat|computacenter|xero|wisetech|technology one|capgemini|atos|teamviewer|temenos|nice ltd",
                 "cap": 16},
    },
    # ───────────────────────── Financials ─────────────────────────
    {
        "id": "intl_banks", "name": "Global Banks", "name_zh": "全球银行",
        "category": "Financials", "category_zh": "金融",
        "thesis": "Major non-US banks across Japan, the UK, Europe, India, Korea and Australia. A direct read on credit and rates.",
        "thesis_zh": "日本、英国、欧洲、印度、韩国与澳洲的大型非美银行。直接反映信贷与利率环境。",
        "rule": {"sectors": ["Financials"],
                 "include": r"\bbank|banking|financial group|financial holding|mitsubishi ufj|sumitomo mitsui|mizuho",
                 "exclude": r"insurance|life|reinsur|asset manage|exchange|invest manage|securit", "cap": 20,
                 "anchors": ["8306.T", "8316.T", "8411.T", "HSBA.L", "BARC.L", "SAN.MC"]},
    },
    {
        "id": "intl_insurers", "name": "Insurers & Diversified Financials", "name_zh": "保险与多元金融",
        "category": "Financials", "category_zh": "金融",
        "thesis": "Insurers, exchanges and diversified financials outside the US. Sensitive to yields, equity markets and book value trends.",
        "thesis_zh": "非美保险、交易所与多元金融公司。受收益率、股市和账面价值趋势影响。",
        "rule": {"sectors": ["Financials"],
                 "include": r"insurance|life ltd|reinsur|assicurazioni|allianz|\baxa\b|generali|aviva|prudential|legal & general|admiral|tokio marine|samsung life|samsung fire|qbe|suncorp|medibank|sompo|dai.ichi|t&d holdings|hiscox|beazley|phoenix group|st james|m&g|aberdeen|schroders|amundi|deutsche boerse|london stock exchange|macquarie|zurich|ms&ad|3i group",
                 "exclude": r"trust plc|investment trust", "cap": 16},
    },
    # ───────────────────────── Healthcare ─────────────────────────
    {
        "id": "intl_pharma", "name": "Global Pharma & Healthcare", "name_zh": "全球制药与医疗",
        "category": "Healthcare", "category_zh": "医疗保健",
        "thesis": "Non-US pharma, biotech and healthcare leaders. Defensive growth with global drug and hospital exposure.",
        "thesis_zh": "非美制药、生物科技与医疗龙头。兼具防御成长、药物管线和医院敞口。",
        "rule": {"sectors": ["Health Care"], "cap": 18},
    },
    # ───────────────────────── Industrials ─────────────────────────
    {
        "id": "intl_defense", "name": "Defense & Aerospace", "name_zh": "国防与航空航天",
        "category": "Industrials", "category_zh": "工业",
        "thesis": "Defense and aerospace leaders outside the US. Tracks rising European and Asian defense spending.",
        "thesis_zh": "非美国防与航空航天龙头。跟踪欧洲和亚洲国防开支上升。",
        "rule": {"sectors": ["Industrials"],
                 "include": r"bae system|rheinmetall|thales|leonardo|saab|rolls.?royce|safran|airbus|babcock|qinetiq|chemring|hensoldt|kongsberg|dassault aviation|mitsubishi heavy|kawasaki heavy|\bihi\b|hanwha aero|hyundai rotem|korea aero|hanwha system",
                 "cap": 14, "anchors": ["BA.L", "RHM.DE", "RR.L", "7011.T"]},
    },
    {
        "id": "intl_automation", "name": "Industrial Automation & Machinery", "name_zh": "工业自动化与机械",
        "category": "Industrials", "category_zh": "工业",
        "thesis": "Automation, robotics and capital-goods leaders tied to capex, factory upgrades and reshoring.",
        "thesis_zh": "自动化、机器人与资本品龙头，受资本开支、工厂升级和回流趋势驱动。",
        "rule": {"sectors": ["Industrials"],
                 "include": r"siemens|schneider|\babb\b|atlas copco|legrand|sandvik|alfa laval|kone|epiroc|spectris|smiths group|fanuc|smc corp|daikin|nidec|yaskawa|misumi|nabtesco|hitachi|mitsubishi electric|omron|smc\b|halma|spirax|rotork|renishaw|schindler|\bgea\b|kion",
                 "exclude": r"heavy|defense", "cap": 16},
    },
    # ───────────────────────── Consumer ─────────────────────────
    {
        "id": "intl_autos", "name": "Autos & Mobility", "name_zh": "汽车与出行",
        "category": "Consumer", "category_zh": "消费",
        "thesis": "Non-US automakers and suppliers. A cyclical read on global demand and the EV transition.",
        "thesis_zh": "非美整车厂与供应商。用于观察全球需求周期和电动车转型。",
        "rule": {"sectors": ["Consumer Discretionary"],
                 "include": r"toyota|honda|nissan|suzuki|mazda|subaru|mercedes|\bbmw\b|volkswagen|porsche|stellantis|renault|hyundai motor|\bkia\b|tata motors|maruti|mahindra & mahindra|bajaj auto|eicher|denso|bridgestone|continental ag|aisin|toyota industries|valeo|forvia|pirelli",
                 "exclude": r"hotel", "cap": 16,
                 "anchors": ["7203.T", "7267.T", "MBG.DE", "BMW.DE", "VOW3.DE"]},
    },
    {
        "id": "intl_luxury", "name": "Luxury & Premium Brands", "name_zh": "奢侈品与高端品牌",
        "category": "Consumer", "category_zh": "消费",
        "thesis": "Luxury, premium spirits and apparel leaders. Tracks pricing power and high-end consumer demand.",
        "thesis_zh": "奢侈品、高端烈酒与服饰龙头。跟踪定价权和高端消费需求。",
        "rule": {"sectors": ["Consumer Discretionary", "Consumer Staples"],
                 "include": r"lvmh|hermes|christian dior|kering|moncler|ferrari|adidas|\bpuma\b|burberry|brunello|prada|essilor|salvatore|richemont|swatch|pernod|diageo|remy|campari|davide campari|l'?oreal",
                 "cap": 16, "anchors": ["MC.PA", "RMS.PA", "OR.PA", "ADS.DE", "DGE.L"]},
    },
    # ───────────────────────── Energy & Materials ─────────────────────────
    {
        "id": "intl_energy", "name": "Global Energy", "name_zh": "全球能源",
        "category": "Energy & Materials", "category_zh": "能源与材料",
        "thesis": "Integrated oil, gas and energy producers outside the US. Sensitive to crude, LNG and global energy demand.",
        "thesis_zh": "非美一体化油气和能源生产商。受原油、LNG 与全球能源需求影响。",
        "rule": {"sectors": ["Energy"], "cap": 14},
    },
    {
        "id": "intl_mining", "name": "Mining & Metals", "name_zh": "矿业与金属",
        "category": "Energy & Materials", "category_zh": "能源与材料",
        "thesis": "Diversified miners and steelmakers outside the US. Cyclical exposure to metals, electrification and China demand.",
        "thesis_zh": "非美多元化矿企与钢铁商。反映金属、电气化和中国需求周期。",
        "rule": {"sectors": ["Materials"],
                 "include": r"\bbhp\b|rio tinto|glencore|anglo american|antofagasta|fortescue|\bvale\b|posco|arcelor|tata steel|\bjsw\b|hindalco|vedanta|south32|mineral resources|boliden|\bnmdc\b|nippon steel|jfe|sumitomo metal|korea zinc|teck",
                 "cap": 16, "anchors": ["BHP.AX", "RIO.L", "GLEN.L", "AAL.L", "FMG.AX"]},
    },
    # ───────────────────────── Communication ─────────────────────────
    {
        "id": "intl_telecom", "name": "Telecom, Media & Internet", "name_zh": "电信媒体与互联网",
        "category": "Communication", "category_zh": "通信",
        "thesis": "Telecom carriers, media and internet platforms outside the US. Mixes defensive cash flow with Asian internet growth.",
        "thesis_zh": "非美电信运营商、媒体和互联网平台。兼具防御现金流和亚洲互联网成长。",
        "rule": {"sectors": ["Communication"], "cap": 16},
    },
    # ───────────────────────── Regional structural-growth sleeves ─────────────────────────
    {
        "id": "intl_india", "name": "India Growth", "name_zh": "印度成长",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "Large-cap India leaders across banks, IT services, telecom, industry and consumer. A broad India growth sleeve.",
        "thesis_zh": "覆盖银行、IT 服务、电信、工业与消费的印度大盘龙头。代表印度成长敞口。",
        "rule": {"countries": ["IN"], "cap": 18},
    },
    {
        "id": "intl_japan", "name": "Japan Inc.", "name_zh": "日本企业",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "Large-cap Japan leaders tied to reflation, corporate reform, exports and capital returns.",
        "thesis_zh": "日本大盘龙头，受再通胀、公司治理改革、出口和资本回报驱动。",
        "rule": {"countries": ["JP"], "cap": 18},
    },
    {
        "id": "intl_korea", "name": "Korea Tech & Industry", "name_zh": "韩国科技与工业",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "Korea's export leaders across memory, internet, autos, batteries, shipbuilding and defense.",
        "thesis_zh": "韩国出口龙头，覆盖存储、互联网、汽车、电池、造船与国防。",
        "rule": {"countries": ["KR"], "cap": 16},
    },
    {
        "id": "intl_uk", "name": "UK Blue Chips", "name_zh": "英国蓝筹",
        "category": "Regional Growth", "category_zh": "区域成长",
        "thesis": "Global-facing UK blue chips in energy, pharma, banks, staples and miners. Dividend-heavy international earners.",
        "thesis_zh": "面向全球的英国蓝筹，覆盖能源、制药、银行、必需消费与矿业。偏高股息、收入国际化。",
        "rule": {"countries": ["GB"], "cap": 18},
    },
]

# Flag emoji per ISO so the page legibly shows the cross-country mix in each member rationale.
FLAG = {"JP": "🇯🇵", "GB": "🇬🇧", "IN": "🇮🇳", "EZ": "🇪🇺", "KR": "🇰🇷", "TW": "🇹🇼", "AU": "🇦🇺"}

CONSTRUCTION = ("Equal-weight baskets, rebalanced monthly, measured against the Intl ex-US "
                "composite.")
HISTORY_NOTE = ("Available history comes from the intl_search cache. Pre-launch series use the "
                "basket's starting membership.")
NOTE = "Curated ex-US theme baskets for monitoring rotation. Descriptive only, not a buy list."


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
