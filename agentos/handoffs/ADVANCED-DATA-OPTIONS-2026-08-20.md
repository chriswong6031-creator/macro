---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad-options-post-entitlement
model: local
ended_because: blocked
mission: >
  Post-entitlement commissioning of merged AD-1. Re-prove live vendor Options
  Snapshot on the production credential. If HTTP 200 + nonempty and the production
  adapter works on a small mixed universe with no production write, stop diagnostics
  and let the normal scheduled nightly produce capture S then D. Do not change
  scoring. Do not start AD-2. Do not backfill 2026-08-14/17/18. Do not switch to
  ThetaData.
state_before: >
  AD-1 runtime (#5872) and AD-1C0 (#5974) merged. Agent OS PR #6018 merged
  2026-08-20T01:48:53Z recording ENTITLEMENT_STILL_BLOCKED from the 19:59Z census.
  Operator then commissioned a post-restoration session. origin/main already carried
  a FAILED 2026-08-19 health receipt from the 01:00Z scheduled capture.
changed:
  - path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md
    what: >
      blocked_by and Context updated with the 2026-08-20T05:23:23Z still-403 census,
      the no-write adapter dry-run, and the failed 2026-08-19 health receipt. AD-1C0
      next_action now records that the first post-merge scheduled capture ran and
      failed. Added do_not_redo against treating a restoration claim as evidence.
  - path: agentos/discoveries/DSC-AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION.md
    what: >
      verified_at moved to 2026-08-20. Falsifier still not triggered. Evidence now
      includes this session's 8-probe + adapter dry-run and the failed health receipt.
      Claim unchanged.
  - path: agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-20.md
    what: >
      New commissioning-session handoff. Verdict remains ENTITLEMENT_STILL_BLOCKED.
      AD1_READY_FOR_SOL_PRODUCTION_ACCEPTANCE_REVIEW is not earned.
verified:
  - claim: origin/main at session start is e186f9f45c1bf0f55e774d836c7ee5df2fecccc7 and contains AD-1, AD-1C0, and #6018
    command: "git fetch origin main; git rev-parse origin/main; git merge-base --is-ancestor 661ad5d291aa687bbb0c7a33e5b573c60a2b148f origin/main; git merge-base --is-ancestor d5ebb5d9b3db8c12deed7c267676cb38b6b348dc origin/main; git merge-base --is-ancestor 537000e9354b6e5e5420760e4d33f14b1b242e07 origin/main"
    result: "origin/main e186f9f45c1bf0f55e774d836c7ee5df2fecccc7 2026-08-19 22:20:39 -0700 'data: nightly timings engine 2026-08-20'; all three merge SHAs are ancestors"
  - claim: option-chain snapshot is still 403 NOT_AUTHORIZED on both vendor domains after the claimed restoration, while stock and news are 200
    command: "RestProber 8-GET census against api.polygon.io and api.massive.com using resolve_key() (MASSIVE_API_KEY), paths /v2/snapshot/.../tickers/AAPL, /v3/snapshot/options/AAPL, /v3/snapshot/options/SPY, /v2/reference/news"
    result: "probe_utc 2026-08-20T05:23:23Z; polygon AAPL stock 200 request_id ab1db468b1d8822828f6b73ccf44f2a3; polygon AAPL chain 403 NOT_AUTHORIZED d9223b2e58b6818ac8fb07bb2e6adea3; polygon SPY chain 403 NOT_AUTHORIZED d2e89fdcdc28380dde77c2e18e66c173; polygon news 200 fcafe59b6b8d547843182e7b46365367; massive AAPL stock 200 f42ce8ada3929b52cf6dd3dd965319e5; massive AAPL chain 403 NOT_AUTHORIZED 8d4202ac5a18633a292285c142ccc74b; massive SPY chain 403 NOT_AUTHORIZED fbe9da5eab0d1b75a929a9a6e5ed870c; massive news 200 df33a37cbc9df49b66109bb4ae71f300; option_chain_200_nonempty=0 of 4"
  - claim: production adapter on a small mixed universe fails the same way and wrote nothing
    command: "PolygonOptions().snapshot(['SPY','QQQ','IWM','AG','CDE'], date(2026,8,19)) after sourcing Macro Dashboard .env; no call to scripts.build_polygon_gex.accrue"
    result: "adapter base_url https://api.polygon.io; key equals local MASSIVE_API_KEY; full universe 375; probe set SPY QQQ IWM AG CDE; census attempted=5 successful=0 failure_reasons.auth_or_entitlement_failure=5 aborted_early=false rows=0; no parquet or health write from this session"
  - claim: the 2026-08-19 scheduled capture is a failed health receipt, not capture S
    command: "git show origin/main:data/polygon_gex_health/2026-08-19.json; git show origin/main:site/options_intel_brief.json; git ls-tree --name-only origin/main data/polygon_gex/chains/"
    result: "session 2026-08-19 capture_instant 2026-08-20T01:00:18.832594+00:00 requested=375 attempted=5 successful=0 coverage_pct=0.0 aborted_early=true decision=nothing_captured health=failed; board_state STALE_SOURCE as_of_session 2026-08-12 oi_counted_date 2026-08-13; newest chain 2026-08-13.parquet"
  - claim: GitHub Actions POLYGON_API_KEY metadata is unchanged since 2026-08-08
    command: "gh api repos/mastermindx-market-intelligence/macro/actions/secrets --paginate --jq '.secrets[] | select(.name==\"POLYGON_API_KEY\" or .name==\"MASSIVE_API_KEY\") | {name, updated_at}'"
    result: "POLYGON_API_KEY updated_at 2026-08-08T08:10:36Z; MASSIVE_API_KEY absent from Actions secrets"
unverified:
  - claim: the GitHub Actions POLYGON_API_KEY byte-equals the local MASSIVE_API_KEY
    what_would_verify: "owner comparison in a secret manager UI; this session must not print or diff key values"
  - claim: the Massive account UI currently shows an Options product as active
    what_would_verify: "owner screenshot of the Massive billing/entitlements page with keys redacted"
  - claim: a written business/enterprise license covering commercial Mastermind use of Options Snapshot exists
    what_would_verify: "owner-supplied vendor contract or written grant on disk"
  - claim: restoration was applied to a different key than the local MASSIVE_API_KEY / Actions POLYGON_API_KEY pair
    what_would_verify: "owner confirms which key id was entitled; this session can only see the locally resolved MASSIVE_API_KEY and the Actions secret name/updated_at"
unresolved:
  - "Vendor Options Snapshot entitlement is still absent on the credential this session can reach. Capture S does not exist. AD-1 is not ready for Sol production-acceptance review."
  - "Missing chain days 2026-08-14/17/18 remain permanent PIT gaps."
next_actions:
  - "OWNER: restore/rebind Options Snapshot + daily OI + Greeks/IV on the key actually used in production (local MASSIVE_API_KEY and/or Actions POLYGON_API_KEY). Cite the 2026-08-20 request IDs if the UI already shows the product as active."
  - "OWNER: confirm a BUSINESS/ENTERPRISE license or written commercial grant before calling AD-1 rights-safe."
  - "After a live 200 + nonempty chain probe AND a no-write adapter success: make zero code changes. Let the next lawful scheduled run replace the failed 2026-08-19 vintage (or stamp the next session) as capture S, then wait for D. Do not --force. Do not call AD-1 live after S alone."
  - "Only after S+D at coverage_pct >= 0.90: run the normal AD-1 production path and return AD1_READY_FOR_SOL_PRODUCTION_ACCEPTANCE_REVIEW."
do_not_redo:
  - "Polygon-vs-Massive domain migration as the cause (falsified 2026-08-19 morning, 2026-08-19T19:59:29Z, and 2026-08-20T05:23:23Z)."
  - "A coding-agent 'fix Polygon options' sweep, base-URL flip, retry inflation, threshold change, or AD-1 scoring edit while the chain endpoint is 403."
  - "Treating an operator restoration claim as live evidence without a same-session 200 + nonempty probe."
  - "375-symbol collector while entitlement is down."
  - "Silent AD-1 route to ThetaData or Cboe delayed-quote scrape."
  - "Manual reconstruction of 2026-08-14/17/18 chain files."
  - "Calling the failed 2026-08-19 health receipt capture S."
  - "Starting AD-2, AD-6, or AD-7."
danger_areas:
  - "data/polygon_gex_health/ is nightly-written runtime state — never commit a diagnostic receipt."
  - "A write into an omitted sparse-tree data/ truncates committed parquet."
  - "HTTP 200 on stocks is not an Options grant and is not a commercial license."
  - "scripts.build_polygon_gex.accrue() writes production chains; commissioning diagnostics must call PolygonOptions.snapshot() only."
discoveries:
  - "DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION"
decisions:
  - "DEC:AD1C0-FIRST-WRITER-QUALITY-RULE"
---

## Owner action packet

Verdict: **ENTITLEMENT_STILL_BLOCKED**.

Return **not** earned: `AD1_READY_FOR_SOL_PRODUCTION_ACCEPTANCE_REVIEW`.

A claimed Massive/Polygon entitlement restoration is not visible to the
production credential this session can reach. HTTP option-chain probes are
still 403 NOT_AUTHORIZED. The current production adapter fails the same way
on a 5-name mixed universe and wrote nothing. Capture S does not exist. The
2026-08-19 scheduled run produced a failed health receipt, which AD-1C0
correctly recorded and which must not be treated as S.

Zero collector/scoring code changes. Zero ThetaData swap. Zero backfill.

### Exact main

Census/artifact SHA: `e186f9f45c1bf0f55e774d836c7ee5df2fecccc7`
(`data: nightly timings engine 2026-08-20`, 2026-08-19 22:20:39 -0700).
Contains #5872, #5974, and #6018. Records land after fast-forward to
`b38c6134d165912e71091386d4e90024ee16f54d` (no overlap with this workstream).

### Safe differential census

Probe time: **2026-08-20T05:23:23Z**.
Key source name: **MASSIVE_API_KEY** (length 32). POLYGON_API_KEY absent from
local env. GitHub Actions secret **POLYGON_API_KEY** exists
(`updated_at` still 2026-08-08T08:10:36Z). No Actions secret named MASSIVE_API_KEY.

| domain | class | HTTP | verdict | body | nonempty | request_id |
|---|---|---|---|---|---|---|
| api.polygon.io | AAPL stock snapshot | 200 | entitled | OK | true | ab1db468b1d8822828f6b73ccf44f2a3 |
| api.polygon.io | AAPL option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | d9223b2e58b6818ac8fb07bb2e6adea3 |
| api.polygon.io | SPY option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | d2e89fdcdc28380dde77c2e18e66c173 |
| api.polygon.io | news | 200 | entitled | OK | true | fcafe59b6b8d547843182e7b46365367 |
| api.massive.com | AAPL stock snapshot | 200 | entitled | OK | true | f42ce8ada3929b52cf6dd3dd965319e5 |
| api.massive.com | AAPL option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | 8d4202ac5a18633a292285c142ccc74b |
| api.massive.com | SPY option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | fbe9da5eab0d1b75a929a9a6e5ed870c |
| api.massive.com | news | 200 | entitled | OK | true | df33a37cbc9df49b66109bb4ae71f300 |

Follow-up AAPL-only per-key probe (MASSIVE_API_KEY only; POLYGON skipped as absent):
polygon `94d2de9e843c4737da0b31b28e9b2794` 403; massive `fd18177e5858fcf28af4c92477a55eaa` 403.

### Production adapter dry-run (no write)

Universe: production auth-probe set `SPY, QQQ, IWM, AG, CDE` (3 index-ETF anchors + 2 basket single names).
Session stamped `2026-08-19`. `accrue()` was not called.

Result: `successful_underlyings=0`, `auth_or_entitlement_failure=5`, `rows=0`.

### What would earn the Sol-review return

1. Same 8-probe shows option-chain HTTP 200 + nonempty results (Greeks/IV/OI present).
2. Same adapter dry-run returns successful_underlyings == 5 with rows > 0, still no production write.
3. Next lawful scheduled capture S: health receipt `healthy`, `coverage_pct >= 0.90`, parquet present, no `--force`.
4. Next lawful OI-count generation D with the same health conditions.
5. Normal AD-1 build observed against S+D. Then and only then:
   `AD1_READY_FOR_SOL_PRODUCTION_ACCEPTANCE_REVIEW`.
