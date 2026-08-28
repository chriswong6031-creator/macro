# CN-B empirical receipts

**Date:** 2026-08-19 · **Pin:** `620acf86f242` · **Seat:** Grok 4.6
Every claim in `CN-B_BAKEOFF.md` that is tagged PRIMARY SOURCE VERIFIED or CODE VERIFIED is backed by one of the rows below.

---

## 1. House access and identity

```text
# secret NAMES only — values never printed
# result: no QICHACHA / QCC_ / TIANYANCHA / TYC_ / QIXIN / AIQICHA names
#         in process env, .env, .env.example
# config.yml only hits are tushare moneyflow/valuation freshness witnesses
```

```text
python3 -c "import pathlib; print(pathlib.Path('engine/entity_resolver.py').read_text()[:800])"
# result: five-layer text→ticker ladder; deferred: learned NER, nicknames, cross-lingual
```

```text
ls data/tushare
# result: broker, chips, forecast, margin, moneyflow, report_rc, valuation
#         no stock_company / USCC / holder-penetration table
```

---

## 2. Tianyancha geo-block (this session)

```text
web_fetch https://www.tianyancha.com/data
web_fetch https://www.tianyancha.com/property/1
# both returned the same interstitial:
#   根据相关法律规定，当前所在地区暂不支持访问
#   Current IP: 104.36.50.55
#   Current location: US
```

Search-indexed official about text (same host, `https://www.tianyancha.com/property/1`):

> 不支持在中华人民共和国境外（仅为本协议之目的，不包括中国香港特别行政区、中国澳门特别行政区及中国台湾地区）的主体注册、登录或访问以及使用境外IP登录或访问。

---

## 3. Qichacha Open API catalog (this session)

```text
web_fetch https://openapi.qcc.com/dataApi
# 167 APIs. Identity-relevant list prices observed 2026-08-19:
```

| ApiCode | Name | List price |
|---|---|---|
| 886 | 企业模糊搜索 (returns USCC) | 0.10 元/次 |
| 410 | 企业工商信息 (USCC, legal name) | 0.20 元/次 |
| 855 | 企业二要素核验 | 0.10 元/次 |
| 735 | 企业工商详情 (shareholders) | 2.00 元/次 |
| 731 | 股东信息(工商登记) | 2.00 元/次 |
| 734 | 变更记录 | 1.00 元/次 |
| 884 | 对外投资核查 | 1.00 元/次 |
| 699 | 上市企业 | 0.50 元/次 |
| 643 | 实际控制人 | 面议 |
| 642 | 股权穿透(四层) | 面议 |
| 628 / 1003 | 受益股东 / 受益所有人 | 面议 |
| 663 | 对外投资穿透(十层) | 面议 |
| 880 / 883 | 所属集团 / 集团成员 | 面议 |
| 921 | 历史工商信息 (曾用名) | 面议 |
| 925 | 历史股东 | 面议 |
| 998 / 991 | 香港企业信息 / 实时 | 面议 |

```text
web_fetch https://mapi.qcc.com/services/protocol/tos
# result: HTTP request failed this session
```

Qichacha 智能体数据平台 user agreement (`https://agent.qcc.com/user-agreement`, updated 2026-06, still the posted page):

- no crawlers; no derivative / competitive products;
- **does not support overseas subjects or overseas IPs** (explicitly including HK/MO/TW for that agreement);
- data obtained through the service **must be stored and used inside the PRC** and must not be transmitted overseas.

That is the agent platform, not the Open API. It is still the live published Qichacha cross-border posture.

---

## 4. GLEIF

```text
GET https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=PetroChina%20Company%20Limited
# 1 record  529900RPY4YG47TRSV05
# registeredAs = 91110000710925462X
# registration.status = LAPSED
# attributes.qcc = QCNUHCT69B
# direct-parent / ultimate-parent = reporting-exception links
```

```text
GET https://api.gleif.org/api/v1/lei-records/529900RPY4YG47TRSV05/direct-parent-reporting-exception
# reason = NO_KNOWN_PERSON
# category = DIRECT_ACCOUNTING_CONSOLIDATION_PARENT
# validFrom / validTo = null
```

```text
GET https://api.gleif.org/api/v1/lei-records/529900RPY4YG47TRSV05/isins
# US71646E2090  (the ADR ISIN — A/H ISINs not in this page)
```

Exact-name batch (same filter, page[size]=3):

| Query | Hits | What came back |
|---|---|---|
| Tencent Holdings Limited | 0 | — |
| Alibaba Group Holding Limited | 1 | LEI 5493001NTNQJDH60PM02, registeredAs **90722**, parent exception, qcc=QKY6NPNEDE |
| Semiconductor Manufacturing International Corporation | 0 | — |
| NIO Inc. | 2 | NIO INC. Cayman 294239 + a Canadian name collision |
| BYD Company Limited | 1 | **BYD Electronic (International)** — wrong legal person |
| China Mobile Limited | 2 | HK company number 21330874 (listed HoldCo, not 600941’s A-share person) |
| Huaneng Power International, Inc. | filter exploded (76k) | one true-ish hit: USCC 91110000625905205U, LEI LAPSED |
| Contemporary Amperex Technology Co., Limited | filter exploded (351k) | garbage |
| WuXi AppTec Co., Ltd. | filter exploded | garbage |
| SAIC Motor Corporation Limited | 0 | — |
| China CSSC Holdings Limited | 0 | — |
| Zijin Mining Group Co., Ltd. | mixed | 91350000157987632G but LEI status DUPLICATE |

---

## 5. Sample frame + CNINFO / Sina

```text
python3 research/alpha_intelligence/censuses/CN-B/build_sample_frame.py
# entities=150 cninfo_targets=111
# cninfo 110/111  (only 300104 乐视网 empty)
# sina holders 23/36
# every 688* attempted in the 36-cut failed
```

Holder gold that names a **group**, not a nominee (截至 2026-03-31 unless noted):

| A-share | Legal name (CNINFO) | Largest holder (Sina) |
|---|---|---|
| 601898 | 中国中煤能源股份有限公司 | 中国中煤能源集团有限公司 |
| 601600 | 中国铝业股份有限公司 | 中国铝业集团有限公司 |
| 601390 | 中国中铁股份有限公司 | 中国铁路工程集团有限公司 |
| 601186 | 中国铁建股份有限公司 | 中国铁道建筑集团有限公司 |
| 601088 | 中国神华能源股份有限公司 | 国家能源投资集团有限责任公司 (as_of 2026-04-07) |
| 600028 | 中国石油化工股份有限公司 | 中国石油化工集团有限公司 |
| 601985 | 中国核能电力股份有限公司 | 中国核工业集团有限公司 |
| 601857 | 中国石油天然气股份有限公司 | 中国石油集团 |
| 601766 | 中国中车股份有限公司 | 中车集团 |
| 601988 / 601939 / 601398 / 601288 | 四大行 | 中央汇金投资有限责任公司 |
| 601328 | 交通银行股份有限公司 | 中华人民共和国财政部 |

Holder gold that is **not** the issuer parent:

| A-share | Legal name | Largest holder | Why it is hostile |
|---|---|---|---|
| 600941 | 中国移动有限公司 | 中国移动香港(BVI)有限公司 | BVI intermediate, not CMCC and not SASAC |
| 002594 | 比亚迪股份有限公司 | HKSCC NOMINEES LIMITED | H-share nominee |
| 601318 | 中国平安保险(集团)股份有限公司 | 香港中央结算(代理人)有限公司 | H-share nominee |
| 601601 | 中国太平洋保险(集团)股份有限公司 | 香港中央结算(代理人)有限公司 | H-share nominee |

CNINFO rename receipt: 600150 公司名称 中国船舶工业股份有限公司, 曾用简称 `中国船舶>> *ST船舶`.

---

## 6. Not run, and why

- Qichacha / Tianyancha / Qixinbao authenticated API calls — no key; overseas clauses.
- GSXT HTML crawl — no API; anti-bot; `QUAL_DATA_COMPLIANCE` §2.4.
- Wind / Choice / iFinD — CN-E’s brief, not this one.
- A 100–200 live vendor accuracy percentage — would be fiction without keys.
