# CN-F — Source and rights registry

**Lane:** GROK-CN-F · **Date:** 2026-08-19 · **Pin:** `12f60066e324`
**Authority:** NONE. No capture is authorized by this table.

How to read a row (same convention as B0):

- **Adopt** = already collected, or the lawful next source for an existing owner.
- **Candidate** = official, rights-plausible, not yet a house owner.
- **Do not ingest** = coincident print, aggregator, or duplicate of an owned clock.
- **Unpinned** = organ exists; dated event tape not located this session.

Redistribution is **not legal advice**. Capture still needs a Data OS source-rights verdict.

---

## 1. Clocks that earned a lobe (candidates)

| Source | Event | Cadence | Machine-readable | Clock | History | Rights / redistribution | Status |
|---|---|---|---|---|---|---|---|
| CDE 药品审评中心 `www.cde.org.cn` — 受理品种 / 审评任务 / 优先审评 / 临床试验默示许可 / 上市药品 | Regulatory-stage change for a named drug + enterprise | Ad hoc; implied-license and 受理 drop as dated list pages | Home HTML 200. List URLs are JS-challenged (HTTP 202) from this egress. No JSON confirmed. | CDE publish date = `source_available_at` | Archive implied by IA; not reconstructed | Official NMPA/CDE disclosure. Derived signals only. | **CANDIDATE** for a BioCatalyst China-regulator extension. Access probe must precede design. |
| China CTR `www.chinadrugtrials.org.cn` 药物临床试验登记与信息公示平台 | Trial registration / status change | Event-driven | Home 200. Search/list 202 JS-challenge. | CTR post date | Analog of ClinicalTrials.gov; depth UNKNOWN | Official. Same derived-signals posture. | **CANDIDATE**, same bio owner. Do not treat as a second bio lobe. |
| MIIT 装备工业一司 公告 `miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2026/art_00d965bfa9ea4bc89bc7613cf911c896.html` (example) | 产品公告 batch + 车船税目录 batch + 购置税减免目录 batch | Irregular numbered batches. Latest this session: 公告2026年第21号, 成文 2026-08-12, 发布 2026-08-13 09:15 | Article HTML has metadata. Payloads are `.doc` attachments. Index is a jpaas shell. | 发布日期 on the 公告 | Batch 409 / 88 / 33 imply long history | Official MIIT 行政许可公告. Do not republish the Word files. | **CANDIDATE** — the EV lobe clock. |

---

## 2. Shared project clock (one organ, two sector labels)

| Source | Event | Cadence | Machine-readable | Clock | History | Rights | Status |
|---|---|---|---|---|---|---|---|
| MEE 建设项目环境影响评价 — 受理 / 拟审查公示 / 已批准公告 `mee.gov.cn/ywgz/hjyxpj/jsxmhjyxpj/` | Project EIA file accepted, proposed for review, approved | Weekly-ish 受理 windows; 拟审查 ad hoc; 批准 as dated decision ranges | HTML tables with 项目名称, 建设地点, 建设单位, 环评机构, 受理日期. Latest acceptance notice 2026-08-06 for window 07-29–08-04. | 公示 date; 受理日期 on the row | 2025–2026 visible on the same columns | Official MEE. 公示 strips secrets by statute (stated on the notice). | **ADOPT into CN-D.** Not a Grid lobe and not a Materials lobe. |
| MEE 全国排污许可证管理信息平台 `permit.mee.gov.cn` | Permit issued / cancelled / revoked | Event + annual execution report | HTML portal 200; list endpoints not row-sampled | Portal publish | UNKNOWN | Official | **CANDIDATE** as a CN-D sibling tape (compliance), not a specialist lobe. Closer to coincident operations than to multi-year lead. |
| NEA 政府信息公开 `zfxxgk.nea.gov.cn` | Energy-project 行政审批 (claimed) | UNKNOWN | Home 200. Linked `xmsp.htm` **404** this session. | Unpinned | Unpinned | Official if the tape exists | **UNPINNED.** Do not invent an NEA 核准 collector from the 404. |

---

## 3. Already owned — do not re-home as a CN specialist lobe

| Source | Why it looks like a clock | House owner | Status |
|---|---|---|---|
| Federal Register + BIS Entity List | Dated export-control / entity-list events that rewire CN semis | `collectors/federal_register.py`, `engine/policy_calendar.py` | **ADOPT.** Semis does not earn a new lobe. |
| US EIA weekly + LBNL queue + `power_scarcity` | Physical US grid/power lead | `collectors/eia.py`, `collectors/lbnl_queue.py`, `engine/power_scarcity.py` | **ADOPT** for US power themes. Not a CN Grid lobe. |
| BioCatalyst (Drugs@FDA, ClinicalTrials.gov, openFDA) | US bio earlier clock | program `biocatalyst` | **ADOPT.** CN CDE/CTR is an *extension of this owner*, not a fork. |
| `china_official` corpora | Dated PRC policy language | `collectors/china_official_corpora.py` (State Council, policy library, PBOC, NDRC, CSRC, People's Daily) | **ADOPT as policy tone.** Explicitly **not** CDE/MIIT/MEE project lists. MIIT list pages already recorded as jpaas-deferred. |
| CPCA `data.cpcadata.com/api/chartlist` | Monthly NEV/ICE wholesale by manufacturer | Cataloged 2026-07-25; JSON 200 this session (2026 YTD in payload); **no collector** | **Do not ingest as the EV lead clock.** Confirmatory coincident print. May later sit under the EV owner as a lagging check. |
| US state gaming (NJ/NV/NY/PGCB) | Operator revenue | `collectors/gaming_*.py` | **Do not ingest as CN 版号.** Wrong market, lagging (~20–25d after month-end, CODE VERIFIED `collectors/gaming_nj.py`). |

---

## 4. Unpinned / do-not-charter

| Source | Why it was a candidate | This session | Status |
|---|---|---|---|
| NPPA 国产网络游戏作品审批 / 版号 batches | The classic CN games lead clock | Organ live; 2018 许可清单 still names the 许可; 头条/要闻/通知公示 are not 版号 batches; guessed historical URLs 404; product query is publisher registry | **UNPINNED.** No lobe. |
| CAC 生成式AI备案 | Possible AI software clock | Homepage 200, news. No structured calendar URL pinned | **UNPINNED.** No lobe. |
| NHSA NRDL negotiation list | Annual reimbursement clock for bio | `nhsa.gov.cn` timed out | **UNKNOWN.** Even if live, it is annual and late vs CDE 受理. Not required to earn the bio lobe. |
| SGCC ecp.sgcc.com.cn | Grid equipment tender lead | 200 SPA shell, no table extracted | **UNPINNED.** Would be Grid-unique if a dated tender tape is later pinned — still not enough this session. |
| NMPA `nmpa.gov.cn` | Parent regulator portal | 412 WAF | Use CDE, not NMPA, as the door. |
