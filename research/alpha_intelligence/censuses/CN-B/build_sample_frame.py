#!/usr/bin/env python3
"""CN-B sample-frame builder.

Builds a 150-entity hostile PRC identity sample from in-repo baskets + A/H pairs
+ a curated unlisted/hostile overlay, then attaches gold from public official
sources already used by the house (CNINFO company profile, Sina top holders).

Does NOT call Qichacha, Tianyancha, Qixinbao, or any login-walled registry.
Does NOT write secrets. Re-runnable. Pace is polite.
"""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = Path(__file__).resolve().parent

CURATED = [
    # VIE / Cayman / red-chip listed issuers (PRC opco is a different legal person)
    {"id": "tencent-holdings", "name_zh": "腾讯控股", "name_en": "Tencent Holdings Limited",
     "tickers": ["0700.HK"], "strata": ["red_chip", "vie_or_holdco", "software"],
     "prc_opco_zh": "深圳市腾讯计算机系统有限公司",
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "HK/Cayman listed holdco; PRC operating company is a different legal person with its own USCC"},
    {"id": "alibaba-group", "name_zh": "阿里巴巴集团", "name_en": "Alibaba Group Holding Limited",
     "tickers": ["9988.HK", "BABA"], "strata": ["vie_or_holdco", "software"],
     "prc_opco_zh": "淘宝（中国）软件有限公司",
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman VIE listed issuer; GLEIF registeredAs is Cayman number 90722, not a USCC"},
    {"id": "meituan", "name_zh": "美团", "name_en": "Meituan",
     "tickers": ["3690.HK"], "strata": ["vie_or_holdco", "software"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman/HK listed; PRC WFOE/VIE stack is the operating graph"},
    {"id": "jd-group", "name_zh": "京东集团", "name_en": "JD.com, Inc.",
     "tickers": ["9618.HK", "JD"], "strata": ["vie_or_holdco"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman listed; PRC opcos are separate legal persons"},
    {"id": "xiaomi-group", "name_zh": "小米集团", "name_en": "Xiaomi Corporation",
     "tickers": ["1810.HK"], "strata": ["red_chip", "vie_or_holdco", "auto"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman listed; auto subsidiary 小米汽车 is a different PRC legal person"},
    {"id": "nio-inc", "name_zh": "蔚来", "name_en": "NIO Inc.",
     "tickers": ["9866.HK", "NIO"], "strata": ["vie_or_holdco", "auto"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman issuer; GLEIF registeredAs=294239 (Cayman), parent reporting exception"},
    {"id": "xpeng", "name_zh": "小鹏汽车", "name_en": "XPeng Inc.",
     "tickers": ["9868.HK", "XPEV"], "strata": ["vie_or_holdco", "auto"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman listed EV; PRC manufacturing entities are subsidiaries/JVs"},
    {"id": "li-auto", "name_zh": "理想汽车", "name_en": "Li Auto Inc.",
     "tickers": ["2015.HK", "LI"], "strata": ["vie_or_holdco", "auto"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman listed EV"},
    {"id": "pinduoduo", "name_zh": "拼多多", "name_en": "PDD Holdings Inc.",
     "tickers": ["PDD"], "strata": ["vie_or_holdco", "historical_rename"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Holdco renamed PDD Holdings; Irish/Cayman stack, PRC opco 上海寻梦信息技术有限公司"},
    {"id": "baidu", "name_zh": "百度", "name_en": "Baidu, Inc.",
     "tickers": ["9888.HK", "BIDU"], "strata": ["vie_or_holdco", "software"],
     "issuer_vs_opco": "listed_holdco_not_prc_opco",
     "hostile_why": "Cayman VIE; 百度在线网络技术（北京）有限公司 is the WFOE"},
    # Unlisted central SOE parents
    {"id": "sasac", "name_zh": "国务院国有资产监督管理委员会", "name_en": "SASAC",
     "tickers": [], "strata": ["central_soe", "control_body"],
     "issuer_vs_opco": "control_body_not_issuer",
     "hostile_why": "Not a company. Often mis-labelled as ultimate parent of every central SOE listed name"},
    {"id": "cnpc-group", "name_zh": "中国石油天然气集团有限公司", "name_en": "CNPC",
     "tickers": [], "strata": ["central_soe", "listed_parent"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted group; parent of 601857. GLEIF marks PetroChina parent as NO_KNOWN_PERSON"},
    {"id": "sinopec-group", "name_zh": "中国石油化工集团有限公司", "name_en": "Sinopec Group",
     "tickers": [], "strata": ["central_soe", "listed_parent"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted group parent of 600028"},
    {"id": "cmcc-group", "name_zh": "中国移动通信集团有限公司", "name_en": "China Mobile Communications Group",
     "tickers": [], "strata": ["central_soe", "listed_parent"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted group; 600941/0941 listed issuer is 中国移动有限公司, a different legal person"},
    {"id": "chn-energy", "name_zh": "国家能源投资集团有限责任公司", "name_en": "CHN Energy",
     "tickers": [], "strata": ["central_soe", "listed_parent", "historical_rename", "power", "mining_chemicals"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "2017 merger of 神华集团 + 国电集团; parent of 601088 中国神华"},
    {"id": "state-grid", "name_zh": "国家电网有限公司", "name_en": "State Grid",
     "tickers": [], "strata": ["central_soe", "listed_parent", "power"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted; listed children 国电南瑞/平高电气/国网信通 are not 'State Grid' the issuer"},
    {"id": "csge-three-gorges", "name_zh": "中国长江三峡集团有限公司", "name_en": "China Three Gorges",
     "tickers": [], "strata": ["central_soe", "listed_parent", "power"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted parent of 600900 长江电力 and 600025 华能水电 / 三峡能源 stack"},
    {"id": "chng-huaneng-group", "name_zh": "中国华能集团有限公司", "name_en": "China Huaneng Group",
     "tickers": [], "strata": ["central_soe", "listed_parent", "power"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted parent of 600011 华能国际"},
    {"id": "cnnc-group", "name_zh": "中国核工业集团有限公司", "name_en": "CNNC",
     "tickers": [], "strata": ["central_soe", "listed_parent", "power"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted parent of 601985 中国核电"},
    {"id": "cetc-group", "name_zh": "中国电子科技集团有限公司", "name_en": "CETC",
     "tickers": [], "strata": ["central_soe", "listed_parent", "semiconductors"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted parent of 002415 海康威视 — actual controller ≠ listed issuer"},
    {"id": "cssc-group", "name_zh": "中国船舶集团有限公司", "name_en": "CSSC",
     "tickers": [], "strata": ["central_soe", "listed_parent", "historical_rename"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Group from CSIC+CSSC merger; listed 600150 was 中船防务 then 中国船舶"},
    # Local SOE parents
    {"id": "shanghai-sasac", "name_zh": "上海市国有资产监督管理委员会", "name_en": "Shanghai SASAC",
     "tickers": [], "strata": ["local_soe", "control_body"],
     "issuer_vs_opco": "control_body_not_issuer",
     "hostile_why": "Municipal SASAC is the controller of 上汽/上海电气, not a company USCC parent"},
    {"id": "saic-group", "name_zh": "上海汽车工业（集团）有限公司", "name_en": "SAIC Group",
     "tickers": [], "strata": ["local_soe", "listed_parent", "auto"],
     "issuer_vs_opco": "unlisted_group_parent",
     "hostile_why": "Unlisted group vs listed 600104 上汽集团 — names collide"},
    # Joint ventures / project companies (unlisted)
    {"id": "saic-gm", "name_zh": "上汽通用汽车有限公司", "name_en": "SAIC-GM",
     "tickers": [], "strata": ["joint_venture", "auto", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "50/50 JV; no single issuer parent; both 上汽 and GM are parents"},
    {"id": "saic-vw", "name_zh": "上汽大众汽车有限公司", "name_en": "SAIC-VW",
     "tickers": [], "strata": ["joint_venture", "auto", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "SAIC–Volkswagen JV; two parents"},
    {"id": "faw-vw", "name_zh": "一汽-大众汽车有限公司", "name_en": "FAW-VW",
     "tickers": [], "strata": ["joint_venture", "auto", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "FAW–Volkswagen JV; listed parents are 一汽解放/一汽富维 not the JV itself"},
    {"id": "gac-toyota", "name_zh": "广汽丰田汽车有限公司", "name_en": "GAC Toyota",
     "tickers": [], "strata": ["joint_venture", "auto", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "GAC–Toyota JV"},
    {"id": "bmw-brilliance", "name_zh": "华晨宝马汽车有限公司", "name_en": "BMW Brilliance",
     "tickers": [], "strata": ["joint_venture", "auto", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "BMW majority after 2022; 华晨集团 bankrupt — historical control flip"},
    {"id": "cnooc-shell-nanhai", "name_zh": "中海壳牌石油化工有限公司", "name_en": "CNOOC and Shell Petrochemicals",
     "tickers": [], "strata": ["joint_venture", "mining_chemicals", "project_company"],
     "issuer_vs_opco": "jv_no_single_parent",
     "hostile_why": "CNOOC–Shell Nanhai petrochemical JV"},
    {"id": "smic-north", "name_zh": "中芯北方集成电路制造（北京）有限公司", "name_en": "SMIC North",
     "tickers": [], "strata": ["joint_venture", "semiconductors", "project_company"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "SMIC Beijing JV/project fab; not the listed 688981 issuer"},
    {"id": "smic-south", "name_zh": "中芯国际集成电路制造（深圳）有限公司", "name_en": "SMIC Shenzhen",
     "tickers": [], "strata": ["project_company", "semiconductors"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "SMIC project company / local fab vehicle"},
    {"id": "ymtc", "name_zh": "长江存储科技有限责任公司", "name_en": "Yangtze Memory Technologies",
     "tickers": [], "strata": ["semiconductors", "project_company", "historical_rename"],
     "issuer_vs_opco": "unlisted_national_project",
     "hostile_why": "Unlisted national memory champion; Unigroup/紫光 history; no listed ticker"},
    {"id": "cxmt", "name_zh": "长鑫存储技术有限公司", "name_en": "ChangXin Memory Technologies",
     "tickers": [], "strata": ["semiconductors", "project_company"],
     "issuer_vs_opco": "unlisted_national_project",
     "hostile_why": "Unlisted DRAM champion; not 兆易创新 the listed distributor/designer"},
    {"id": "hua-hong-grace", "name_zh": "上海华虹宏力半导体制造有限公司", "name_en": "Hua Hong Grace",
     "tickers": [], "strata": ["semiconductors", "project_company", "joint_venture"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "Opco under 华虹半导体 1347.HK / 688347.SS; names collide with listed issuer"},
    {"id": "cgn-yangjiang", "name_zh": "阳江核电有限公司", "name_en": "Yangjiang Nuclear Power",
     "tickers": [], "strata": ["project_company", "power", "joint_venture"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "CGN project company; listed parent is 1816.HK / 003816.SZ 中国广核"},
    {"id": "ctg-xiluodu", "name_zh": "三峡金沙江川云水电开发有限公司", "name_en": "CTG Jinsha River Chuan Yun",
     "tickers": [], "strata": ["project_company", "power"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "Three Gorges project company sitting under 长江电力 / 三峡集团"},
    {"id": "spic-huanghe", "name_zh": "国家电投集团黄河上游水电开发有限责任公司", "name_en": "SPIC Huanghe Hydropower",
     "tickers": [], "strata": ["project_company", "power", "central_soe"],
     "issuer_vs_opco": "project_sub_of_listed",
     "hostile_why": "SPIC project/regional company; listed cousins 600886 国投电力 / 600021 上海电力"},
    # Delisted / relisted / ADR drop
    {"id": "leeco-delisted", "name_zh": "乐视网信息技术（北京）股份有限公司", "name_en": "LeEco / Leshi Internet",
     "tickers": ["300104.SZ"], "strata": ["delisted_relisted"],
     "listing_status": "delisted",
     "hostile_why": "A-share delisted; ticker 300104 is a dead listing key; USCC survives"},
    {"id": "luckin-relisted", "name_zh": "瑞幸咖啡", "name_en": "Luckin Coffee Inc.",
     "tickers": ["LKNCY"], "strata": ["delisted_relisted", "vie_or_holdco"],
     "listing_status": "relisted_otc",
     "hostile_why": "Nasdaq delist 2020 then OTC/relist path; Cayman issuer"},
    {"id": "didi", "name_zh": "滴滴出行", "name_en": "DiDi Global Inc.",
     "tickers": ["DIDIY"], "strata": ["delisted_relisted", "vie_or_holdco"],
     "listing_status": "us_delisted",
     "hostile_why": "US-listed then privatisation/delist pressure; PRC opco 北京小桔科技有限公司"},
    {"id": "petrochina-adr-gone", "name_zh": "中国石油天然气股份有限公司", "name_en": "PetroChina Company Limited",
     "tickers": ["601857.SS", "0857.HK"], "strata": ["delisted_relisted", "a_h", "central_soe"],
     "listing_status": "adr_delisted_ah_live",
     "hostile_why": "NYSE ADR delisted 2022-09-08; A+H remain. Same legal person, fewer listing keys"},
    # Historical rename listed (extra to baskets)
    {"id": "crrc-merger", "name_zh": "中国中车股份有限公司", "name_en": "CRRC Corporation Limited",
     "tickers": ["601766.SS", "1766.HK"], "strata": ["historical_rename", "a_h", "central_soe"],
     "former_names_zh": ["中国南车股份有限公司", "中国北车股份有限公司"],
     "hostile_why": "2015 CNR+CSR merger; two predecessor legal persons / tickers folded"},
    {"id": "cssc-holdings-rename", "name_zh": "中国船舶工业股份有限公司", "name_en": "China CSSC Holdings",
     "tickers": ["600150.SS"], "strata": ["historical_rename", "central_soe"],
     "former_names_zh": ["中船防务", "沪东重机"],
     "hostile_why": "Listed name/ticker continuity hides legal-name and group-parent changes"},
]

SECTOR_BASKETS = {
    "cn_semis": "semiconductors",
    "cn_pharma_cxo": "pharma",
    "cn_autos": "auto",
    "cn_soe_value": "central_soe",
    "cn_metals": "mining_chemicals",
    "cn_coal": "mining_chemicals",
    "cn_gold": "mining_chemicals",
    "cn_rare_earth": "mining_chemicals",
    "cn_battery": "auto",
    "cn_med_devices": "pharma",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _a_code(ticker: str) -> str | None:
    t = ticker.replace(".SS", "").replace(".SZ", "").replace(".BJ", "")
    if len(t) == 6 and t.isdigit():
        return t
    return None


def load_house_listed() -> list[dict]:
    mem = json.loads((ROOT / "data/baskets_china/membership.json").read_text())
    pairs = json.loads((ROOT / "data/hk_ah_panel/pairs.json").read_text())
    by_ticker: dict[str, dict] = {}

    for bid, tag in SECTOR_BASKETS.items():
        basket = mem["baskets"][bid]
        for m in basket["members"]:
            if m.get("removed"):
                continue
            t = m["ticker"]
            rec = by_ticker.setdefault(t, {
                "id": t.lower().replace(".", "-"),
                "name_zh": m.get("name_zh"),
                "tickers": [t],
                "strata": [],
                "source": "house_basket",
                "basket_ids": [],
            })
            if tag not in rec["strata"]:
                rec["strata"].append(tag)
            rec["basket_ids"].append(bid)

    ah_map = {p["a"]: p["h"] for p in pairs}
    for a, h in ah_map.items():
        rec = by_ticker.setdefault(a, {
            "id": a.lower().replace(".", "-"),
            "name_zh": None,
            "tickers": [a],
            "strata": [],
            "source": "house_ah_panel",
            "basket_ids": [],
        })
        if h not in rec["tickers"]:
            rec["tickers"].append(h)
        if "a_h" not in rec["strata"]:
            rec["strata"].append("a_h")

    return list(by_ticker.values())


def fetch_cninfo(symbol: str) -> dict:
    import akshare as ak

    df = ak.stock_profile_cninfo(symbol=symbol)
    if df is None or df.empty:
        return {"ok": False, "error": "empty"}
    row = df.iloc[0].to_dict()
    # stringify NaNs
    clean = {}
    for k, v in row.items():
        if v is None:
            continue
        s = str(v)
        if s in {"None", "nan", "NaT"}:
            continue
        clean[k] = s
    return {"ok": True, "fields": clean}


def fetch_sina_holders(symbol: str) -> dict:
    import akshare as ak

    df = ak.stock_main_stock_holder(stock=symbol)
    if df is None or df.empty:
        return {"ok": False, "error": "empty"}
    cols = [c for c in ["股东名称", "持股比例", "股本性质", "截至日期", "公告日期"] if c in df.columns]
    rows = []
    for _, r in df.head(5).iterrows():
        rows.append({c: (None if str(r[c]) in {"nan", "None"} else str(r[c])) for c in cols})
    return {"ok": True, "top5": rows}


def main() -> None:
    listed = load_house_listed()
    curated = []
    seen_ids = {r["id"] for r in listed}
    for c in CURATED:
        if c["id"] in seen_ids:
            # merge strata
            for rec in listed:
                if rec["id"] == c["id"]:
                    for s in c.get("strata", []):
                        if s not in rec["strata"]:
                            rec["strata"].append(s)
                    rec.update({k: v for k, v in c.items() if k not in rec or rec[k] in (None, [], "")})
                    break
            continue
        curated.append({**c, "source": "curated_hostile"})
        seen_ids.add(c["id"])

    entities = listed + curated
    # trim listed-only overflow to keep ~150, preferring multi-stratum + AH
    if len(entities) > 160:
        listed_sorted = sorted(
            listed,
            key=lambda r: (len(r.get("strata", [])), "a_h" in r.get("strata", []), r["id"]),
            reverse=True,
        )
        keep_listed = listed_sorted[: 150 - len(curated)]
        entities = keep_listed + curated

    # Gold pulls
    a_codes = []
    for rec in entities:
        for t in rec.get("tickers") or []:
            c = _a_code(t)
            if c:
                rec.setdefault("a_code", c)
                a_codes.append((rec["id"], c))
                break

    print(f"entities={len(entities)} cninfo_targets={len(a_codes)}", flush=True)
    cninfo_ok = 0
    for i, (eid, code) in enumerate(a_codes, 1):
        rec = next(r for r in entities if r["id"] == eid)
        try:
            got = fetch_cninfo(code)
        except Exception as e:  # noqa: BLE001 — receipt the failure
            got = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        rec["cninfo_profile"] = got
        if got.get("ok"):
            cninfo_ok += 1
            f = got["fields"]
            rec["legal_name_zh"] = f.get("公司名称") or rec.get("name_zh")
            rec["legal_name_en"] = f.get("英文名称") or rec.get("name_en")
            rec["former_short_zh"] = f.get("曾用简称")
            rec["list_date"] = f.get("上市日期")
            rec["setup_date"] = f.get("成立日期")
            rec["h_code_cninfo"] = f.get("H股代码")
        print(f"  cninfo {i}/{len(a_codes)} {code} ok={got.get('ok')}", flush=True)
        time.sleep(1.2)

    # Hostile listed parent gold via Sina top holders (public)
    hostile_codes = []
    for rec in entities:
        tags = set(rec.get("strata") or [])
        if rec.get("a_code") and tags.intersection(
            {"a_h", "central_soe", "historical_rename", "delisted_relisted", "semiconductors", "pharma", "auto", "power"}
        ):
            hostile_codes.append(rec["a_code"])
    hostile_codes = list(OrderedDict.fromkeys(hostile_codes))[:36]
    holder_ok = 0
    print(f"sina_holder_targets={len(hostile_codes)}", flush=True)
    by_code = {r.get("a_code"): r for r in entities if r.get("a_code")}
    for i, code in enumerate(hostile_codes, 1):
        rec = by_code[code]
        try:
            got = fetch_sina_holders(code)
        except Exception as e:  # noqa: BLE001
            got = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        rec["sina_top_holders"] = got
        if got.get("ok") and got.get("top5"):
            holder_ok += 1
            rec["gold_largest_holder"] = got["top5"][0].get("股东名称")
            rec["gold_holder_as_of"] = got["top5"][0].get("截至日期")
        print(f"  holders {i}/{len(hostile_codes)} {code} ok={got.get('ok')}", flush=True)
        time.sleep(1.2)

    # stratum counts
    counts: dict[str, int] = {}
    for rec in entities:
        for s in rec.get("strata") or ["untagged"]:
            counts[s] = counts.get(s, 0) + 1

    payload = {
        "schema": "cn_b_prc_entity_sample.v1",
        "built_at": _now(),
        "n": len(entities),
        "stratum_counts": dict(sorted(counts.items())),
        "gold": {
            "cninfo_ok": cninfo_ok,
            "cninfo_n": len(a_codes),
            "sina_holder_ok": holder_ok,
            "sina_holder_n": len(hostile_codes),
        },
        "identity_rule": "Vendor IDs are never Mastermind canonical identity. Canonical keys are USCC (PRC legal person), LEI when issued, and listing keys (exchange ticker / ISIN) as aliases.",
        "entities": entities,
    }
    out = OUT_DIR / "CN-B_SAMPLE_FRAME.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out} n={payload['n']} cninfo={cninfo_ok}/{len(a_codes)} holders={holder_ok}/{len(hostile_codes)}")


if __name__ == "__main__":
    main()
