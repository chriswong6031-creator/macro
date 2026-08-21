---
key: B1-PROPHET-PUBLIC-SPLIT
question: >
  How is the B1 exposure (DSC:PROPHET-INDEX-PUBLIC-R2-TWIN — the full US Prophet
  plan book anonymously readable at the public R2 dev URL while the origin 401s
  the same path) closed: what is the canonical contract split, who serves each
  consumer, and what makes the closure structural rather than a one-time delete?
answer: >
  Sol architecture ruling, Day-5 directive 2026-08-21. (1) prophet/index.json is
  the full, decision-bearing Prophet plan book; that contract is premium/private:
  full book → one canonical prophet.index/* contract → protected origin /
  authenticated server-side producer-consumer paths → never anonymously
  retrievable from public R2. (2) Public operational metadata is a SEPARATE
  explicitly public contract: R2 key prophet/health.json, schema
  prophet.public_health/v1, carrying only the minimum non-decision-bearing
  publication metadata proven required by public-safe instrumentation
  (source_asof for the rescue watchdog's freshness comparison, plus publication
  identity: published_at, checkpoint sha, index_sha256). (3) A temporary
  same-key redacted prophet/index.json bridge (schema prophet.index_bridge/v1,
  source_asof only) is authorized as containment ONLY while consumers migrate —
  it is not the finished architecture. (4) Consumer rebinds: prophet_rescue
  reads prophet/health.json with amended verdict semantics (a health receipt is
  not the user-serving data plane); build_prophet_marks --publish reads the
  canonical accepted bytes via git (origin/main:site/prophet/index.json), never
  a public URL; the Terminal's /api/flow prophet_idx keeps backend-first
  (/api/hub/prophet) and loses its public-R2 fallback — backend unavailable
  means fail closed, not fall through anonymously; any other legitimate
  full-book consumer (Mastermind) rebinds to an authenticated/private path.
  (5) Producer closure is structural: the daily.yml post-checkpoint publisher
  publishes ONLY the health projection; prophet/index.json becomes a forbidden
  public key enforced by a runtime guard in the R2 upload path, a nightly
  self-healing tombstone (the publisher deletes the forbidden key if it ever
  reappears), and CI tests that fail any reintroduction of the old write.
  (6) Do not create two permanently different payload contracts both named
  prophet/index.json; do not build a new private-R2 resilience plane in this
  wave. B1 closes only when the independent §8b reviewer can state: BOUNDARY
  PASS — no unauthenticated path to withheld Prophet plan rows was
  constructible under production configuration.
rationale: >
  The estate's own law (premiumdata/factordata 404 on the public host, and
  config/r2_delivery_plane_classification.v1.json rows prophet_full_board_product
  / prophet_full_board_repository_static classified PREMIUM_PRODUCT with
  "withdraw full static bytes, R2" migration dependencies) already treats
  premium payloads as R2-public-forbidden; prophet/index.json predated the
  artifact becoming a paid boundary and slipped past it. The P-MP1-SHELL
  migration (#6076) moved the US board's paid boundary onto this artifact, so
  the server-side split was bypassable in one unauthenticated GET, and the §8b
  boundary certification was explicitly withheld pending this closure.
alternatives:
  - option: Permanent redacted same-key public prophet/index.json (Day-4 sketch)
    why_not: >
      Sol rejected two permanently different payload contracts under one name;
      the redacted twin would be a second contract called prophet/index.json and
      would keep inviting consumers to bind to the public key. The same-key
      bridge is authorized only as temporary containment.
  - option: Ship IDs/counts in the public health projection because the Day-4
      sketch mentioned them
    why_not: >
      Default-deny — Sol requires proving which fields each surviving consumer
      actually requires. The rescue lane demonstrably compares only source_asof;
      nothing public-safe needs 262 commercial records or their IDs.
  - option: Authenticated private R2 mirror for the full book (availability plane)
    why_not: >
      Explicitly deferred by Sol: no new private-R2 resilience plane in this
      wave merely to preserve fallback redundancy; commission separately against
      an explicit resilience requirement if later warranted.
  - option: One-time delete of the public object without producer closure
    why_not: >
      The daily.yml publisher recreates the object every nightly the index
      changes; removal once is insufficient. Closure must make republication
      structurally impossible (guard + tombstone + CI mutation test).
evidence:
  - "Anonymous GET https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json = 200, 2,242,608B, 269 plans (2026-08-21T04:00Z) vs origin 401 on the same path"
  - "Producer: .github/workflows/daily.yml post-checkpoint conditional publisher (~2857-3060) via scripts/build_prophet.py R2_INDEX_KEY:125"
  - "prophet_rescue.py consumes only source_asof from the R2 object (:851); fetch failure is silent (fetch_r2_index → (None, err)), so the tombstone cannot alert it — the health rebind restores the leg"
  - "build_prophet_marks.py --publish is R2-only fail-closed (:244-266) and refuses on schema != prophet.index/v1 (:1315), so the bridge no-ops it cleanly; invoked by ops/launchd/com.mastermind.prophetmarks.plist inside 09:25-16:05 ET"
  - "Terminal terminal/app/api/flow/route.ts tryFetch: backend first, generic R2 fallback (:354-376), prophet_idx → prophet/index.json (:108)"
related:
  - "DSC:PROPHET-INDEX-PUBLIC-R2-TWIN"
  - "WS:PROPHET-US-V4-RECOVERY"
reversibility: >
  Reversible by a superseding Sol/operator ruling: the guard constants, tests,
  and tombstone are ordinary code. The bridge is self-expiring (deleted at
  cutover step 8). Re-publishing the full book publicly would require reverting
  the guard, the tests, and the publisher — deliberately loud.
---

Recorded by the Day-5 Prophet Lab session executing Sol's B1 ruling. The ordered
cutover (census → containment → health contract → rebinds → producer closure →
tombstone → proofs → §8b re-review) and its receipts live in the day-5 handoff
under agentos/handoffs/.
