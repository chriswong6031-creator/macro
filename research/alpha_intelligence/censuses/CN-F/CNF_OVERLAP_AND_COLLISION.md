# CN-F — Overlap and collision map

**Lane:** GROK-CN-F · **Date:** 2026-08-19 · **Pin:** `12f60066e324`

What every later builder MUST consume. What they must never rebuild.

---

## 1. Adopt (do not fork)

| Need | Adopt | Never |
|---|---|---|
| US bio clock | program `biocatalyst`; `engine/biocatalyst/`; `collectors/biocatalyst/`; `collectors/openfda.py`; `collectors/clinicaltrials.py`; `collectors/fda_shortages.py` | A second bio program named "China BioCatalyst" with its own event spine |
| US defense / procurement clock | `WS:DEFENSE-PROCUREMENT-V3`; `engine/government_revenue/` | SAM/USAspending copy for CN SOEs |
| US power physical clock | `engine/power_scarcity.py`; `collectors/lbnl_queue.py`; `collectors/eia.py` | A CN "power_scarcity" that reimplements FRED/EIA |
| US semis export-control clock | `collectors/federal_register.py`; `engine/policy_calendar.py` Entity-List sub-signal | A CN semis lobe whose only earlier clock is BIS |
| China policy language | `collectors/china_official_corpora.py` (State Council, PBOC, NDRC, CSRC, People's Daily) | Adding CDE/MIIT/MEE project lists into that corpora collector as "just another organ" without a dedicated PIT contract |
| China project EIA | Sibling **CN-D** (project EIA source map) | A Grid lobe **and** a Materials lobe on the same MEE tape |
| PRC entity / SOE identity | Sibling **CN-B**, **CN-C**; `engine/stock_identity/` | A per-sector issuer mapper |
| China sector display hub | `research/CHINA_SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md` (Shenwan/THS rotation page) | A specialist lobe that is actually a second sector-central |
| Native-data probe law | `scripts/probe_china_sources.py` + CNH-R3 (manual only) | Wiring new sector probes into nightly |
| Commodity→sector transmission | C1 prereg (`research/C1_COMMODITY_SECTOR_PREREG.md`) | Relabeling C1 as a CN materials lobe |
| Evidence mesh / adapters | PASS-0 responsibility C: adapter builds wait for K1 | A specialist warehouse |

---

## 2. In-flight collisions

| Lane / artifact | Collision with CN-F | Rule |
|---|---|---|
| CN-D project EIA source map | Owns the only live CN project clock this census found | Grid/Materials **wait**. Cite, do not parallel-collect. |
| CN-B PRC entity resolver | Bio CDE enterprise names and EIA `建设单位` both need it | Mapping is CN-B's job. Sector lanes consume the resolver. |
| CN-C SOE demand | EIA owners this session are 国铁集团, 大唐, 国家能源集团, 中煤, 中石化 | Demand-side read is CN-C. EIA is the project clock, not a second SOE lobe. |
| BioCatalyst #5906 (PASS-0 named in-flight) | CN CDE/CTR is an extension of this owner | No China bio build until BioCatalyst owner accepts the extension. |
| PASS-0 C adapter freeze | Specialist *builds* wait for Evidence Mesh K1 | This census does not authorize collectors. |
| `#5822` CN institutional masterplan | Institutional, not sector-clock | Do not fold 版号/CDE/MIIT into 13F-shaped work. |
| `DNR:KILL-CN-SUPPLY-ABSORPTION` | Kills a price-only 减持 absorption construct | Does not kill EIA/MIIT/CDE clocks. Do not cite it as a sector-lobe ban. |
| `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` | Limit-up tape | Irrelevant to this census. Do not smuggle CN clocks onto the adjusted tape. |
| `DNR:KILL-COMMODITY-XSEC-MOM` | Commodity momentum factor | Does not kill MEE EIA. |

---

## 3. False friends (look like clocks, are not)

| Item | Why it fails the bar |
|---|---|
| CPCA monthly NEV wholesale | Same-month sales print. Confirms MIIT catalogs after the fact. |
| China news wire / `china_official` 政策 | Generic, not sector-unique, not issuer-mapped. |
| `china_sector_cycles` 版号 narrative | A cycle story, not a dated event tape. |
| US NJ/NV/NY gaming revenue | Lagging, wrong market. |
| HuggingFace / GitHub repo collectors | Coincident developer activity, not a CN AI license clock. |
| SHFE/CZCE inventory and positioning | Coincident commodity tape. |
| XLV → Shenwan pharma read-through | Cross-market confirmer, not NMPA. |
| NDRC notices inside china_official | Policy language. Not MIIT 第409批 and not MEE 受理 tables. |

---

## 4. Neural Web lobe bar (do not launder this census into lobes)

`research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md` §1: a lobe owns its own objective, FDR family, and falsifiers. This census identifies **source clocks**. It does not charter Neural Web lobes, rails, or waves.

`DNR:KILL-SLOT-PRERESERVATION`: a census proves testability, never entitlement. Two YES rows here are **candidates for an existing owner**, not reserved lobe slots.
