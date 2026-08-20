# CN-C probe receipts — 2026-08-19

**When:** 2026-08-19T07:39Z–07:50Z.  
**From:** `104.36.50.55` AS203020 HostRoyale (ipinfo.io). UA Chrome 124 macOS. TLS verify off (several mainland chains incomplete). Timeout 12–20s.  
**Not a collector.** Bodies were truncated; no `data/` write.

## Reachability

| URL | HTTP | Note |
|---|---|---|
| `https://www.ccgp.gov.cn/` | 200 | title 中国政府采购网; 采购意向/招标/中标 tokens present |
| `http://search.ccgp.gov.cn/` | 200 | 236 B “努力加载中…” then search HTML |
| `https://search.ccgp.gov.cn/` | 502 | nginx |
| `http://search.ccgp.gov.cn/bxsearch?…&kw=国家电网&timeType=2` | 200 | filter chrome (类型 includes 公开招标…终止公告) |
| same search `timeType=6` (2nd query) | 200 | title **频繁访问!** ; IP printed |
| `http://www.ccgp.gov.cn/cggg/zygg/gkzb/` | 200 | 公开招标公告 list, 2026-08-19 |
| `http://www.ccgp.gov.cn/cggg/zygg/zbgg/` | 200 | 中标公告 list |
| `http://www.ccgp.gov.cn/cggg/zygg/zbgg/202608/t20260819_27163657.htm` | 200 | award 公告概要 + 供应商 table |
| `http://www.ccgp.gov.cn/cggg/zygg/gkzb/202608/t20260819_27163632.htm` | 200 | tender 预算金额 / 开标时间 |
| `http://cgyx.ccgp.gov.cn/cgyx/pub/pubSearch` | 200 | 政府采购意向公开 ; **验证码** |
| `https://www.ccgp.gov.cn/cggg/zygg/htgg/` | 404 | no central 合同 channel |
| `https://www.ccgp.gov.cn/robots.txt` | 404 | |
| `http://pub.ccgp.gov.cn/` | 403 | |
| `https://www.ggzy.gov.cn/` | 200 | Vue; 今日公告数量 templates |
| `https://www.ggzy.gov.cn/deal/dealList.html` | 200 | `{{ item.time }}` |
| `https://www.ggzy.gov.cn/data/platform.js` | 200 | 66 KB provincial platform registry |
| `https://deal.ggzy.gov.cn/` | NXDOMAIN | |
| `https://www.cebpubservice.com/` | 405 | 访问被阻断 |
| `https://ctbpsp.com/` | 405 | same WAF |
| `https://www.sgcc.com.cn/` | timeout | |
| `https://ecp.sgcc.com.cn/` | 200 | redirect `…/ecp2.0/portal/#/` ; title 国家电网新一代电子商务平台 ; `$_ts` packer |
| `https://ecp.sgcc.com.cn/ecp2.0/portal/assets/js/config.202608131951.js` | 200 | `baseUrl=/ecp2.0/` ; login `/isc/newlogin.html` ; `ecp_wcm_core=/ecp2.0/ecpwcmcore/` ; `isEncrypt:false` |
| `https://ecp.sgcc.com.cn/ecp2.0/ecpwcmcore/` | 404 | bare GET |
| `https://ecp.sgcc.com.cn/isc/newlogin.html` | 200 | |
| `https://ecp.sgcc.com.cn/robots.txt` | 404 | |
| `https://mall.sgcc.com.cn/` | NXDOMAIN | |
| `https://www.csg.cn/` | 200 | 中国南方电网 |
| `https://www.bidding.csg.cn/` | 200 | 供应链统一服务平台 |
| `https://www.bidding.csg.cn/zbgg/1200439658.jhtml` | 200 | tender ; `项目编号： CG1500022002349952` ; `发布时间： 2026-08-19 11:15:24` |
| `https://www.bidding.csg.cn/zbhxrgs/1200439681.jhtml` | 200 | **中标结果公告** ; `采购编号： CG0000022002324473` ; 中标人 named |
| `https://www.bidding.csg.cn/contract/index.jhtml` | 200 | login 供货商协同, not a notice list |
| `https://www.bidding.csg.cn/xygg/index.jhtml` | 200 | 寻源 ; newest samples 2023–24, first item a 退款函 |
| `https://www.bidding.csg.cn:9090/gmp/login.html` | 200 | |
| `https://www.csgmall.cn/` | timeout | |
| `https://ecp.csg.cn/` | NXDOMAIN | |
| `https://ygp.gdzwfw.gov.cn/` | 200 | 广东省公共资源交易平台 ; Vue `/ggzy-portal/` |
| `http://jsggzy.jszwfw.gov.cn/` | 200 | 江苏省公共资源交易网 |
| `https://ggzyfw.beijing.gov.cn/` | SSL BAD_ECPOINT | |
| `http://www.ccgp-jiangsu.gov.cn/` | 200 | 江苏政府采购网 |
| `http://www.ccgp-jiangsu.gov.cn/jiangsu/js_cggg/details.html?gglb=gkzb&ggid=5a5424043b67413f9c63707d8e300470` | 200 | 公告进度 includes 采购意向公开 … **合同公告** ; 不得转载 |
| `https://www.epec.com/` | 200 | 易派客 (Sinopec) |
| `https://www.chnenergy.com.cn/` | 200 | names 国能e招 |
| `https://www.chnenergybidding.com.cn/` | 200 | **151-byte empty body** |
| `https://eps.ctg.com.cn/` | 200 | 中国三峡集团电子采购平台 |
| `https://ecp.chng.com.cn/` | NXDOMAIN | |
| `https://www.ndrc.gov.cn/` | 200 | Server: WAF |
| `https://www.mof.gov.cn/` | 200 | JS redirect shell |

## Field extracts (verbatim-enough)

**CCGP award** `t20260819_27163657.htm`: 采购项目名称 / 品目 / 采购单位 / 行政区域 / 公告时间 / 评审专家名单 / 总中标金额 ￥17.490934 万元 / 供应商名称 泰安盈科广告传媒有限公司 / 货物数量 “详见附件” / 得分表 80.69 vs 73.40 vs 66.73.

**CCGP tender** `t20260819_27163632.htm`: 品目 服务/商务服务/审计服务 / 预算金额 ￥60.000000万元 / 开标时间 2026年09月09日 09:30 / 采购单位 `SPD-28`.

**CSG tender** `/zbgg/1200439658.jhtml`: 南网科研院2026年6月高压专业科技类公开招标项目采购(二次招标) ; 招标人 南方电网科学研究院有限责任公司 ; 2 标包 ; 预计采购金额 / 最高投标限价 table present.

**CSG award** `/zbhxrgs/1200439681.jhtml`: title 中标公告 (folder is 公示公告) ; 中标人 广东华工精卓数智创新科技有限公司 ; asks winner to log in to download 中标通知书.

## Instability

CCGP channel paths flipped 200 ↔ 502 across minutes (`/cggg/zygg/`, `/fbgg/`). Search is one-shot then 频繁访问. Do not cron either.
