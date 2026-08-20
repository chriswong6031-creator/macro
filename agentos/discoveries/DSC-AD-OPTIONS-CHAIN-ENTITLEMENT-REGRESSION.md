---
key: AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION
claim: >
  Between 2026-08-13 evening and 2026-08-14 the linked Polygon/Massive key lost its
  option-chain snapshot entitlement: /v3/snapshot/options/{symbol} answers HTTP 403
  NOT_AUTHORIZED for every probed underlying on BOTH https://api.polygon.io and
  https://api.massive.com, while stock-snapshot and news endpoints answer 200 with the
  SAME key on BOTH domains, interactively and in the scheduled nightly identically. The
  vendor-domain-migration hypothesis is therefore falsified as a cause (the two domains
  behave byte-identically for this key), parser/spot/orchestration/execution-context are
  all exonerated (spot() succeeds, chain() raises 403 before parse_chain is reached),
  and data/polygon_gex/chains is frozen at 2026-08-13 with sessions 08-14/17/18
  unrecoverable (OI is point-in-time; no lawful backfill exists). Before AD-1C0, the
  outage surfaced only as run_status polygon_gex_accrual {"status":"empty"} because
  _one_chain() collapsed every failure root to None — the nightly also burned ~1,125
  doomed requests (~13 min) per run retrying 375 symbols x3.
falsifier: >
  A secret-safe probe (scripts/massive_entitlement_probe.py idiom) returning HTTP 200
  with nonempty results on /v3/snapshot/options/AAPL for the configured key on either
  domain; or the nightly's polygon_gex_accrual reporting successful_underlyings > 0
  with the same key. Either observation means the entitlement is restored (or the key
  was replaced) and this record's operational consequences lapse.
so_what: >
  Restoring the entitlement is an OWNER/vendor account action — no code change can fix
  it, and a lib/ticker-style workaround must not be attempted. Until restoration plus
  TWO consecutive lawful scheduled captures (session S and its OI-count day D) at
  >=0.90 coverage, AD-1 (Daily EOD Options Intelligence Brief, PR #5872) stays
  BUILT_NOT_PROVEN and production commissioning is SOURCE-BLOCKED — do not "prove" it
  with --ignore-staleness. After AD-1C0, an auth outage is visible as
  auth_or_entitlement_failure in the accrual census/health receipts and short-circuits
  after a 5-symbol mixed-class probe instead of sweeping the universe.
kind: constraint
verified_at: 2026-08-20
verified_by: >
  Post-entitlement commissioning census 2026-08-20T05:23:23Z (RestProber 8-GET,
  key source MASSIVE_API_KEY) plus production adapter dry-run: both
  api.polygon.io and api.massive.com still return HTTP 403 NOT_AUTHORIZED on
  /v3/snapshot/options/{AAPL,SPY} and HTTP 200 on AAPL stock snapshot and news.
  PolygonOptions.snapshot([SPY,QQQ,IWM,AG,CDE], 2026-08-19) returned 5/5
  auth_or_entitlement_failure, 0 rows, no production write. Request IDs in
  agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-20.md. A claimed restoration
  did not trigger this record's falsifier. Prior coordinator reproof
  2026-08-19T19:59:29Z and nightly collect remain consistent.
  data/massive/capability_manifest.json (2026-08-08T11:47:39Z, key_source
  POLYGON_API_KEY) still records options_chain_snapshot HTTP 200 entitled with
  Greeks/IV/OI.
scope: [macro]
confidence: verified
workstream: "WS:ADVANCED-DATA-OPTIONS"
evidence:
  - "Post-entitlement census 2026-08-20T05:23:23Z: 8-probe still chain 403 / stock+news 200 on both domains; adapter dry-run 5/5 auth_or_entitlement_failure"
  - "Scheduled health receipt data/polygon_gex_health/2026-08-19.json on origin/main: health=failed coverage_pct=0.0 aborted_early 5/5 auth_or_entitlement_failure capture_instant 2026-08-20T01:00:18Z"
  - "Coordinator reproof 2026-08-19T19:59:29Z: 8-probe table, both domains x {AAPL stock, AAPL chain, SPY chain, news}; chain 403 NOT_AUTHORIZED; stock/news 200"
  - "Live differential census 2026-08-19 (session 25dc7757 census packet): 8-probe table, both domains x {AAPL stock, AAPL chain, SPY chain, news}"
  - "Nightly collect job 95560690668 (run 32077948964): 375 underlyings, 403 Forbidden per symbol x3 attempts, 'snapshot empty — nothing accrued'"
  - "data/massive/capability_manifest.json (2026-08-08): options_chain_snapshot then 'entitled' (200, greeks/IV/OI present) under POLYGON_API_KEY"
  - "data/polygon_gex/chains/ on origin/main — newest 2026-08-13.parquet; 2026-08-14/17/18 absent"
---

The Aug-8 committed manifest proves the capability existed under this key ladder five
days before it vanished; the chain store advanced through 08-13 afterward. The regression
is therefore a vendor-side plan/entitlement change, not a repo-side integration break.
Related: DEC:AD1C0-FIRST-WRITER-QUALITY-RULE (the durability layer built in response),
WS:ADVANCED-DATA-OPTIONS wave AD-1C0.
