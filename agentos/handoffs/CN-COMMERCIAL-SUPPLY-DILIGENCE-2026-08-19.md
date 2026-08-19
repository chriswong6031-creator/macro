---
workstream: WS:CN-COMMERCIAL-SUPPLY-DILIGENCE
session: grok/cn-e-commercial-supply-diligence
model: local
ended_because: complete
mission: >
  GROK-CN-E commercial supply-chain / alt-data diligence. Compare Wind PDB/SDB,
  Choice/iFinD graph APIs, other licensed PRC corporate/supply-chain providers,
  and mobile/ecommerce only as secondary lines. Recommend a purchase only where
  it cuts normalization debt and is lawful for Mastermind-derived use.
state_before: >
  No WS, no commercial supply-chain diligence packet. SKIP-ALL (2026-07-05)
  already cut paid supply-chain from long-hold. The 2026-07 China qual audit
  rated Wind/Choice/iFinD stretch with UNVERIFIED prices. china_filings.py is
  metadata-only. Zero Wind/Choice/iFinD integrations. TuShare spine is
  foundation-only pending a written commercial grant.
changed:
  - {path: research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md, what: "GROK-CN-E diligence: no-buy verdict, evaluation matrix, primary-source license quotes"}
  - {path: agentos/workstreams/WS-CN-COMMERCIAL-SUPPLY-DILIGENCE.md, what: "new workstream; W0 done; parked pending OEM grant"}
  - {path: agentos/decisions/DEC-CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE.md, what: "do not buy a seat; reopen only on written persist+derive+display grant"}
  - {path: agentos/discoveries/DSC-CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY.md, what: "public licences are internal-use; they do not license Mastermind display"}
  - {path: agentos/handoffs/CN-COMMERCIAL-SUPPLY-DILIGENCE-2026-08-19.md, what: "this file"}
verified:
  - {claim: "QCC public ToS forbids redistribution and derivative/scoring products", command: "python3 -c \"from pathlib import Path; t=Path('research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md').read_text(); assert 'resell, sublicense, redistribute' in t and 'scoring system' in t; print('qcc-quotes-present')\"", result: "qcc-quotes-present"}
  - {claim: "china_filings.py remains metadata-only (no PDF bodies)", command: "python3 -c \"from pathlib import Path; t=Path('collectors/china_filings.py').read_text(); assert 'No PDF bodies are ever fetched' in t; print('metadata-only')\"", result: "metadata-only"}
  - {claim: "no Wind/iFinD/Choice API client in collectors/", command: "python3 -c \"import pathlib; hits=[]; 
[hits.append(str(p)) for p in pathlib.Path('collectors').rglob('*.py') for pat in ['wind.com.cn','51ifind','quantapi.eastmoney','WindPy'] if pat.lower() in p.read_text(errors='replace').lower()]; print(hits or 'none')\"", result: "none"}
  - {claim: "agentos records validate", command: "python3 scripts/agentos.py validate", result: "0 errors"}
unverified:
  - {claim: "Wind WFT click-wrap, Choice contract, and iFinD contract contain the same internal-use / no-redistribution clauses as QCC", what_would_verify: "fetch the actual PDF/click-wrap from a seated account, or a sales-returned OEM draft, and quote the persist/derive/display clauses"}
  - {claim: "commercial (non-campus) CSMAR would still bar customer-facing derived display", what_would_verify: "a CSMAR commercial contract PDF"}
  - {claim: "Wind PDB/SDB row counts, A/H join keys, and historical vintage depth", what_would_verify: "WDS data dictionary or a seated export of SDB for one dual-listed issuer across two annual-report years"}
unresolved:
  - "No vendor was asked for a quote. This packet is documentary diligence, not a sales conversation."
  - "Wind PDB/SDB have no first-party landing page with a public data dictionary; naming is from the CEIBS/Sohu 2022–2024 announcements."
next_actions:
  - "Do not purchase and do not open a vendor thread from this packet."
  - "Leave disclosure-graph work on the public CNInfo 年报 floor; entity resolution stays with CN-B."
  - "Reopen WS:CN-COMMERCIAL-SUPPLY-DILIGENCE only if a written OEM grant names API + persist + derive + customer-facing derived display."
do_not_redo:
  - "Do not buy a terminal because it has 产业链 or 供应链 screens (DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE)."
  - "Do not treat campus CSMAR/CNRDS as a product source."
  - "Do not substitute a KYC/工商 graph for 年报 top-5 disclosure edges."
  - "Do not ingest legal-rep / UBO / director PII as a supply-chain spine (QUAL_DATA_COMPLIANCE §4.4)."
  - "Do not cite DNR:KILL-CN-SUPPLY-ABSORPTION as forbidding this diligence, and do not treat this diligence as resurrecting that factor."
danger_areas:
  - "A WDS FileSync or QCC offline dump looks like persist. Public terms still confine it to internal systems and (for QCC) forbid derivative products."
  - "Tianyancha is geo-blocked from the US. Do not design a collector that assumes the operator's default network can reach it."
  - "TuShare personal tokens are still non-commercial. Do not launder a Tushare graph as a Wind substitute."
  - "Session worktrees are sparse. This packet is research-only and must not write into omitted data/ or site/ trees."
prs: []
decisions: [DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE]
discoveries: [DSC:CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY]
---

GROK-CN-E is done. Do not buy a commercial PRC supply-chain or registry seat
for Mastermind-derived use. The public license record forbids or fails to grant
persist + derive + customer-facing display. The public CNInfo 年报 top-5 table
remains the lawful floor. Full matrix and quotes live in
`research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md`.
