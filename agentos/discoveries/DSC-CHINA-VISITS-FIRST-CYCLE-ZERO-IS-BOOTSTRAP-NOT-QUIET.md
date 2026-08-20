---
key: CHINA-VISITS-FIRST-CYCLE-ZERO-IS-BOOTSTRAP-NOT-QUIET
claim: >
  A zero-row first cycle from collectors/china_visits.py — and from ANY future
  downstream collector that filters china_filings on a category born in the same
  merge — is a structural bootstrap artifact, never evidence of a quiet filing
  day and never evidence the classifier lost filings. Mechanism, measured on the
  first natural post-merge asia-close run (32372312243 -> commit a14ac56627c9):
  scripts/collect.py runs china_visits BEFORE china_filings in its serial loop
  (16:37:07Z vs 16:44:45Z), so china_visits scans the CHECKOUT-era
  data/china_filings/filings.parquet — one full cycle behind — and a category
  minted by the very merge under test cannot exist in that store yet. The same
  commit that carried the n_candidates=0 receipt also carried 73 raw
  keyword-matching filings (68 业绩说明会 dated 2026-08-20, 5 投资者关系活动记录表
  dated 2026-08-19), ALL 73 already stored category=institutional_visit — a 100%
  classifier hit rate. Nothing was lost: filings.parquet dedup is keep-FIRST on
  announcementId, the china_visits candidate filter
  (filings[filings["category"]=="institutional_visit"], collectors/china_visits.py:375)
  is not date-gated, and coverage.json's coverage_start is bookkeeping, not a
  filter — so the next natural run surfaces every one of the 73. The one-cycle
  latency itself is documented as deliberate at scripts/collect.py:248 ("reads
  the PRIOR night's china_filings store (one-cycle latency, not a defect)").
falsifier: >
  The next natural asia-close run after commit a14ac56627c9 reports
  n_candidates < 68 for china_visits, or persists zero rows to
  data/china_visits/visits.parquet while the store still holds the 73
  institutional_visit rows. Either outcome refutes the bootstrap attribution
  and makes P1 genuinely BROKEN (bounded repair: order china_visits after
  china_filings in scripts/collect.py's serial loop). More generally: any
  first-cycle zero where the checkout-era store ALREADY held rows of the new
  category refutes the mechanism.
so_what: >
  Never grade a new china_filings-derived category's first production cycle as
  QUIET_DAY on a zero — the observation window structurally excludes same-day
  filings, so the honest verdicts are bootstrap-artifact (store carries raw
  matches, correctly categorized) or BROKEN (store carries raw matches the
  category plane lost), decided by reading the raw titles at the receipt
  commit, not the stored category alone. And never "repair" the serial-loop
  order off a first-cycle zero — the latency is a documented design property;
  changing it is a product ruling (it trades a permanent 1-day visit-surface
  delay), not a defect fix. Attribution receipt: China Alpha WS wave p1,
  P1-ZERO-ROW-ATTRIBUTION 2026-08-20.
kind: landmine
verified_at: 2026-08-20
verified_by: >
  Proof-only researcher session (Sol-authorized P1-ZERO-ROW-ATTRIBUTION task,
  2026-08-20): gh run view 32372312243 --log (china_visits 16:37:07Z
  n_candidates=0; china_filings 16:44:45Z, szse 6300 raw / 2642 net-new);
  git show a14ac56627c9:data/china_filings/filings.parquet + pandas keyword
  scan (73/73 raw-match = stored institutional_visit); git show of
  coverage.json/health.json at the same commit; run headSha 666ff40c confirmed
  ancestor of both the predecessor store commit and a14ac56627c9.
scope: [macro, collectors/china_visits.py, collectors/china_filings.py, scripts/collect.py]
confidence: verified
---

The category-priority design amplifies the trap in the OTHER direction too:
institutional_visit is the LOWEST named category in china_filings.py's
CATEGORY_PRIORITY, so a genuine visit filing whose title also contains a
higher-priority keyword (investigation/inquiry_letter/holder_change families)
classifies away from the visits plane by design. On 2026-08-20 that loss was
zero (73/73 agreement), but a future zero-or-low day should re-run the raw
keyword scan against stored categories before trusting the candidate count.
