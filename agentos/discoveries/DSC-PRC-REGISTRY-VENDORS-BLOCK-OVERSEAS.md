---
key: PRC-REGISTRY-VENDORS-BLOCK-OVERSEAS
claim: >
  Tianyancha contractually and empirically refuses overseas subjects and
  overseas IPs, and Qichacha’s posted 2026-06 agent-platform agreement does
  the same plus forbids storing or querying the obtained data outside the
  PRC. Mastermind has no Qichacha/Tianyancha/Qixinbao key. These vendors
  therefore cannot be the PRC legal-person resolver from the current
  US-operated seat.
falsifier: >
  `curl -sS -A 'MastermindResearch/0.1' https://www.tianyancha.com/property/1`
  returning a 200 page that no longer contains the overseas-subject /
  overseas-IP ban, AND `curl -sS -o /dev/null -w '%{http_code}'
  https://openapi.qcc.com/api/` (or the signed Open-API host) returning
  authenticated USCC+legal-name JSON for 中国石油天然气股份有限公司 from
  the production runtime IP, with the signed contract on disk permitting
  persistence. Either half failing keeps the claim standing.
so_what: >
  Do not spend a build wave on Qichacha/Tianyancha/Qixinbao collectors.
  Do not store qcc / 天眼查企业ID as identity (GLEIF already emits a
  `qcc` mapping field — treat it as an alias, never as the key). For PRC
  legal-person identity use USCC + LEI + listing keys; for parent/control
  use dated CNINFO/HKEX/annual-report facts. Re-open only under the four
  flip conditions in research/alpha_intelligence/censuses/CN-B/CN-B_BAKEOFF.md.
kind: constraint
confidence: verified
verified_at: 2026-08-19
verified_by: >
  web_fetch https://www.tianyancha.com/data and
  https://www.tianyancha.com/property/1 from US IP 104.36.50.55 (geo-block
  interstitial); search-indexed official Tianyancha about text on overseas
  subjects/IPs; web_fetch https://openapi.qcc.com/dataApi (167-API catalog);
  posted Qichacha agent user-agreement overseas + in-PRC-storage clauses;
  process-env/.env/config.yml key-name scan (no QCC/TYC/QIXIN names);
  GLEIF GET lei-records/529900RPY4YG47TRSV05 (qcc=QCNUHCT69B,
  parent reporting-exception reason=NO_KNOWN_PERSON).
scope: [macro]
---

CN-B bake-off receipt: `research/alpha_intelligence/censuses/CN-B/CN-B_BAKEOFF.md`.
This is an access/rights constraint, not a quality ranking of the vendors’
onshore products.
