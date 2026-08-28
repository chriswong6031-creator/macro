---
key: CN-PROJECT-CODE-LIVES-ON-LOCAL-EIA
claim: >
  The join key for China physical-expansion intelligence is the 24-digit 项目代码
  printed on municipal/provincial EIA cover forms and local DRC 备案/核准 pages.
  National tzxm (new.tzxm.gov.cn) is the ID authority and a captcha 验证 widget,
  not an anonymous project search. MEE national 已批准公告 is the wrong harvest
  for battery plants — the 2026-07-13–30 list was five ports/mines and zero C3841
  rows. One industrial site routinely fragments into several codes (cell plant,
  110 kV hookup, lab, box line, even a solar line on a Fudi campus).
falsifier: >
  A public, anonymous national tzxm or MEE search that returns the 24-digit codes
  and GWh for the §4 battery plants in
  research/CN_PROJECT_EIA_CAPACITY_SOURCE_MAP_2026-08-19.md (e.g. 泉州时代
  2603-350583-04-03-243140, 盐城弗迪 2108-320924-89-01-663305) as structured
  rows, without opening a municipal EIA PDF. Or a single project code that covers
  both the 罗源时代 cell plant and its two 2026 grid hookups.
so_what: >
  A future collector starts at municipal 生态环境局 公示 + EIA PDF cover forms
  in 闽/苏/粤/渝/皖/鲁, keys on 项目代码, stores role (cell|module|lab|hookup|
  campus_other), and never sums GWh across roles or name-matches 时代/弗迪 to a
  ticker. Do not build against national tzxm 办理结果公示 or MEE 已批准公告 as
  the battery universe. Re-probe provincial tzxm from the Studio — this session's
  datacenter egress 403/412/reset several provincial hosts.
kind: data
confidence: verified
verified_at: 2026-08-19
verified_by: >
  research/CN_PROJECT_EIA_CAPACITY_SOURCE_MAP_2026-08-19.md §1–§4 and
  research/cn_project_eia/PILOT_20_LITHIUM_BATTERY_PROJECTS_2026-08-19.json;
  curl 200 on new.tzxm.gov.cn, mee.gov.cn 已批准 2026-07-31 announcement
  (five non-battery approvals), and 20 official EIA/DRC artifacts opened
  2026-08-19.
scope: [macro]
---

Pilot industry pick in the same map: lithium-ion battery manufacturing (C3841).
Display-tier only; no Prophet / sizing authority.
