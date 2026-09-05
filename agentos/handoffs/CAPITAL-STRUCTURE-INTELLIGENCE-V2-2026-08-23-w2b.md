---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2b-capacity
model: codex
ended_because: blocked
mission: >
  Qualify and implement one bounded W2B capacity change on the existing natural
  Capital Structure carrier, prove that it preserves W1/W2A law, and return one
  exact draft pull request to Sol before merge without starting W3 or W4.
state_before: >
  W2A was done and naturally proven by run 32603557988 and generation
  73d9810fe3f9, but its effective 180 LIVE slots admitted 202 current-run rows,
  producing honest arrival overflow 22 and leaving inherited LIVE debt. W2B had
  Chairman authority only for a qualified 500/20/20 capacity envelope on the
  same carrier.
changed:
  - path: collectors/sec_capital_structure.py
    what: >
      Made LIVE_TAIL=500, RECOVERY=20, and HISTORICAL_BACKFILL=20 the one
      canonical reservation map and derived MAX_FILINGS_PER_RUN=540 from its
      sum. No scheduler, source, identity, queue, carrier, cadence, or authority
      behavior changed.
  - path: tests/test_sec_capital_structure.py
    what: >
      Pinned the canonical map and added hostile all-485, empty-recovery spill,
      500/501 overflow, total-cap, lane-fairness, and protected recovery/history
      cases while carrying existing W2A scheduler tests to the new envelope.
  - path: tests/test_capital_structure_ingestion_health.py
    what: >
      Pinned honest horizon behavior at 500/501 and proved zero arrival overflow
      cannot hide inherited LIVE debt.
  - path: research/CAPITAL_STRUCTURE_W2B_CAPACITY_QUALIFICATION_2026-08-23.md
    what: >
      Recorded the mandatory carrier stop/go census, exact natural runtime
      baseline, conservative cap-540 projection, SEC pacing/storage behavior,
      anchor-correct maximum-cohort replay, downstream load, and falsifiers.
  - path: docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md
    what: >
      Froze W2A/W2B capacity law without changing W2A class, lane, spill,
      horizon, projection, identity, or authority semantics.
  - path: agentos/decisions/DEC-CS-V2-W2B-500-LIVE-ENVELOPE.md
    what: >
      Recorded the Chairman-authorized capacity choice, rejected carrier/source
      expansion and freshness redefinition, and bound acceptance to the first
      natural scheduled post-merge chain.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: >
      Kept W2/W2B in progress, retained W2A as done/proven, bound W3/W4 to W2,
      and recorded PR #6287 plus this handoff.
  - path: agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-23-w2b.md
    what: >
      Added this cold-stranger Sol-return packet and natural-proof continuation.
prs: [6287]
verified:
  - claim: W2B-0 qualifies cap 540 on the existing daily carrier.
    command: >
      Read data/ops/nightly_timings/collect.jsonl and GitHub job metadata for
      runs 32426513915, 32534736736, and 32603557988; compute the slowest recent
      per-filing SEC band against the largest recent non-CS remainder.
    result: >
      Cap-540 SEC projection 58.122m plus non-CS 126.475m equals whole-collect
      184.597m: 19.403m below the existing 204m warning and 55.403m below the
      240m hard cap. Serial 0.12s pacing, retries, timeouts, runner, carrier,
      cadence, and tripwires are unchanged. Natural attempts had zero SEC 429s.
  - claim: The observed maximum cohort clears under the unchanged W2A scheduler.
    command: >
      Read-only replay of the 2026-08-14 discovery cohort with all preceding
      registration anchors retained; compare raw IDs, policy-eligible queue IDs,
      selected IDs, class quotas, and overflow.
    result: >
      485 raw rows; 484 policy-eligible/admitted; all 484 selected; overflow 0;
      one unanchored issuer row excluded before queue admission. The hostile
      test conservatively admits and selects all 485 while preserving RECOVERY
      20, HISTORICAL 20 plus 15 spilled slots, and all seven lanes.
  - claim: W2B is capacity-only and W2A scheduling law is byte-stable.
    command: >
      git diff main-at-start f3f618c2c783 -- collectors/sec_capital_structure.py;
      AST hashes for select_retrieval_queue and _fair_lane_rows at base/current.
    result: >
      Collector production diff contains only the reservation map, derived cap,
      and explanatory comment. select_retrieval_queue hash
      b1acc6dfbd0ae08c381e7548c82b4fb4d5b00c64bb7823c1af454f28029b4edc
      and _fair_lane_rows hash
      e9ac41695db5a2d8ac08c55fbe4fbe78a0ec3d28d6f6a94517e15b28264006a1
      are identical at base and W2B.
  - claim: Current downstream direct-document load does not increase.
    command: >
      Read committed discovery, coverage, attempts, and source manifest; replay
      base W2A 160/20/20 cap200 and W2B 500/20/20 cap540 on the same queue; count
      REGISTRATION_FEE_FORMS.
    result: >
      W2A selects 200 with 57 fee roots; W2B selects 540 with the identical 57
      fee-root set. Latest Capital Structure wall remains the observed 65.0m of
      90m and the direct-document compiler 63m27s.
  - claim: Hostile and cross-wave regression suites pass.
    command: >
      PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m pytest
      --noconftest -q over the 12 W1/W2A/W2B Capital Structure test targets and
      two append-only fence nodes named in PR #6287; independent Sol invocations
      over 227 core cases and 49 append/source cases.
    result: >
      Owner integrated 253 passed; focused scheduler/health 80 passed.
      Independent Sol 227 plus 49 passed, 276 total. Only three unrelated pytest
      temporary-directory cleanup warnings appeared; no assertion failed.
  - claim: W1 identity, closed bundles, projection, authority, append fence, and #5792 remain fixed.
    command: >
      Named evidence-identity/closed-bundle/projection/daily/fence tests; source
      hash compare of ingestion_health.decide_verdict; cmp and SHA-256 of
      projection.json and site/capital-structure-data/latest.json; jq authority.
    result: >
      #5792 function source SHA-256 remains
      74cd0a97e34a13308d1f4c291c7f300ed950c1056c7e549a0c4bc2d562e342ca.
      Canonical/public twins are byte-identical at SHA-256
      a0242a1f0180365bea10f8d66dbe05fb39439a47270fa6bb5491f35cd68a09c3.
      prophet_authority=false in ingestion, health, telemetry, and projection;
      W2B changes no identity, manifest, compiler, projection, or fence source.
  - claim: Independent preliminary Sol review passed the settled implementation.
    command: >
      Read-only Sol review of all seven pre-handoff W2B files, scoped repo/PR
      census, production-ledger replays, independent tests, timing arithmetic,
      Agent OS validation, diff check, and scope audit.
    result: >
      PASS with no P0, P1, P2, or P3 finding. This was implementation review,
      not merge, deployment, natural proof, or W2 completion authority.
  - claim: Agent OS records are valid and sequencing remains bounded.
    command: python3 scripts/agentos.py validate
    result: >
      0 errors. W2/W2B remain in_progress; W2A remains done/proven; W3/W4 remain
      todo and depend on W2. Unrelated pre-existing warnings do not touch W2B.
unverified:
  - claim: Exact final PR head has concluded binding CI and explicit Sol release.
    what_would_verify: >
      Wait for every required check on draft PR #6287 to conclude, repair only
      attributable failures, then obtain Sol review/release of that exact head.
  - claim: W2B is merged or naturally proven in production.
    what_would_verify: >
      Only after explicit Sol release and merge, observe the first natural
      scheduled daily whose collect checkout contains the merge; do not dispatch
      a duplicate or rerun healthy work.
unresolved:
  - "Inherited LIVE debt remains real; cap 540 prevents new debt only inside the supported <=500 arrival envelope."
  - "A future admitted cohort above 500, SEC rate-limit response, timing breach, or invariant failure returns to Sol."
  - "W3 and W4 are unstarted and unauthorized."
next_actions:
  - Keep PR #6287 draft, unarmed, auto-merge null, and explicitly HOLD-FOR-SOL.
  - Own binding CI through terminal state; repair only genuine attributable W2B failures.
  - Return the exact final PR head and receipts to Sol; do not merge without explicit release.
  - After release and merge only, monitor the first natural scheduled chain; never dispatch a duplicate daily.
do_not_redo:
  - Dispatch a daily or rerun healthy production work before or after merge.
  - Change W2A classification, precedence, lane fairness, spill, horizon, identity, fence, projection, or authority law.
  - Add an SEC source, queue, store, cadence, job, carrier, timeout, or larger cap under this wave.
  - Hide inherited debt behind zero current-arrival overflow or call a fresh compiler generation a current information horizon.
  - Start W3 or W4.
danger_areas:
  - "The 500 envelope is an observed and commissioned operating bound, not a claim about every future SEC session."
  - "The dedicated r2_capital_structure 403 is a storage-probe result with an existing r2_research fallback, not an SEC pacing response."
  - "A green PR and preliminary Sol PASS are not a merge release or natural production proof."
decisions:
  - DEC:CS-V2-W2B-500-LIVE-ENVELOPE
---

W2B is implemented and qualified but remains held before merge. W2 and W2B stay
in progress until the first natural post-merge chain proves the capacity change.
