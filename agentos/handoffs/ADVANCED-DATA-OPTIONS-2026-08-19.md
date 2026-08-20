---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad-options-source-restore
model: local
ended_because: blocked
mission: >
  Recover the canonical EOD options-chain source and move merged AD-1 from
  BUILT_NOT_PROVEN / SOURCE_BLOCKED toward production acceptance. First reprove
  live vendor entitlement. Write code only if a repo defect remains after the
  account is entitled. Do not change the AD-1 scoring model. Do not start AD-2.
state_before: >
  AD-1 runtime (#5872) and AD-1C0 (#5974) already merged on origin/main. The
  workstream still described #5872 as awaiting review/CI. site/options_intel_brief.json
  was STALE_SOURCE as_of_session 2026-08-12 / oi_counted_date 2026-08-13. Chain
  store frozen at 2026-08-13. Prior 2026-08-19 handoff still treated both PRs as
  unmerged. DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION already named vendor
  Options entitlement as the cause.
changed:
  - path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md
    what: >
      Reconciled stale awaiting_review / AD-1 awaiting_ci claims. Status now blocked
      on vendor Options Snapshot entitlement. AD-1 and AD-1C0 marked done with merge
      SHAs; AD-2 added as todo/CLOSED until AD-1 production acceptance; Theta/Cboe/
      domain-migration landmines and do_not_redo entries added.
  - path: agentos/discoveries/DSC-AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION.md
    what: >
      Reproof evidence from this session's 8-probe (2026-08-19T19:59:29Z) appended.
      Claim unchanged: entitlement still absent; falsifier not triggered.
  - path: agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-19.md
    what: >
      Replaced same-day AD-1C0-merge-era handoff with this entitlement-reproof
      owner-action packet. Prior file contents remain in git history.
verified:
  - claim: origin/main at session census contains both AD-1 and AD-1C0 merge commits
    command: "git merge-base --is-ancestor 661ad5d291aa687bbb0c7a33e5b573c60a2b148f HEAD; git merge-base --is-ancestor d5ebb5d9b3db8c12deed7c267676cb38b6b348dc HEAD; gh pr view 5872 --json state,mergedAt,mergeCommit; gh pr view 5974 --json state,mergedAt,mergeCommit"
    result: "both ancestors true; 5872 MERGED 2026-08-19T13:25:26Z oid 661ad5d291aa687bbb0c7a33e5b573c60a2b148f; 5974 MERGED 2026-08-19T16:04:26Z oid d5ebb5d9b3db8c12deed7c267676cb38b6b348dc"
  - claim: live option-chain snapshot is 403 NOT_AUTHORIZED on both vendor domains while stock and news are 200
    command: "RestProber 8-GET census against api.polygon.io and api.massive.com using resolve_key() (MASSIVE_API_KEY), paths /v2/snapshot/.../tickers AAPL, /v3/snapshot/options/AAPL, /v3/snapshot/options/SPY, /v2/reference/news"
    result: "probe_utc 2026-08-19T19:59:29Z; polygon AAPL stock 200 request_id c1b8700d10d72ed465a13a3ead2dcb77; polygon AAPL chain 403 NOT_AUTHORIZED fd56f7ecc3704901de3576d65367940e; polygon SPY chain 403 NOT_AUTHORIZED 9cff3f7301be3aba1c3dda1e39117a16; polygon news 200 77eb7f3e064ad400299497120902353a; massive AAPL stock 200 bc1226e6afcfcafa24604d9c65e81a20; massive AAPL chain 403 NOT_AUTHORIZED 50ee12b44116050356665b9b526b9ef5; massive SPY chain 403 NOT_AUTHORIZED d057e08c0960818fd6afd0ae0ef4edeb; massive news 200 5398152bf120b6fd9e36d17475023384"
  - claim: AD-1 artifact is still source-stale and chain store is still frozen at 2026-08-13
    command: "python3 json load site/options_intel_brief.json top-level; ls data/polygon_gex/chains/2026-08-*.parquet; ls data/polygon_gex_health; python3 extract data/run_status.json sources.polygon_gex_accrual"
    result: "board_state STALE_SOURCE as_of_session 2026-08-12 oi_counted_date 2026-08-13 opportunities/directional_watch/event_board len 0; newest chain 2026-08-13.parquet; 2026-08-14/17/18 absent; polygon_gex_health directory absent; polygon_gex_accrual status empty date 2026-08-18 checked_at 2026-08-19T04:42:05Z"
  - claim: 2026-08-08 capability manifest recorded entitled options_chain_snapshot under POLYGON_API_KEY
    command: "python3 extract data/massive/capability_manifest.json rest.options_chain_snapshot and key_source and probed_at_utc"
    result: "probed_at_utc 2026-08-08T11:47:39Z key_source POLYGON_API_KEY http_status 200 verdict entitled has_greeks/IV/OI true results_count 5"
  - claim: GitHub Actions has POLYGON_API_KEY and no MASSIVE_API_KEY secret
    command: "gh api repos/mastermindx-market-intelligence/macro/actions/secrets --paginate --jq '.secrets[] | select(.name==\"POLYGON_API_KEY\" or .name==\"MASSIVE_API_KEY\") | {name, updated_at}'"
    result: "POLYGON_API_KEY updated_at 2026-08-08T08:10:36Z; MASSIVE_API_KEY absent from Actions secrets"
  - claim: ThetaData collector is not wired into AD-1 / polygon_gex
    command: "rg -n thetadata|ThetaData|THETA scripts/build_polygon_gex.py collectors/polygon_options.py engine/options_intel_brief.py scripts/build_options_intel_brief.py"
    result: "zero matches on those four AD-1 path files; capabilities live in collectors/thetadata.py on the separate theta-ops lane"
unverified:
  - claim: the GitHub Actions POLYGON_API_KEY byte-equals the local MASSIVE_API_KEY
    what_would_verify: "owner comparison in a secret manager UI; this session must not print or diff key values"
  - claim: the Massive account UI currently shows an Options Starter/Developer/Advanced or business Options product as active
    what_would_verify: "owner screenshot of the Massive billing/entitlements page with keys redacted"
  - claim: a written business/enterprise license covering commercial Mastermind use of Options Snapshot exists
    what_would_verify: "owner-supplied vendor contract or written grant on disk"
unresolved:
  - "Vendor Options Snapshot entitlement is still absent. Owner must restore/rebind it on the linked key under a rights-safe commercial grant."
  - "First post-#5974 scheduled capture has not run. data/polygon_gex_health/ is still absent. Do not hand-write it."
  - "Missing chain days 2026-08-14/17/18 remain permanent PIT gaps."
next_actions:
  - "OWNER: inspect the Massive account that owns POLYGON_API_KEY (GitHub Actions secret, updated 2026-08-08T08:10:36Z) and local MASSIVE_API_KEY. Restore Options Snapshot + daily OI + Greeks/IV. Cite request IDs in this handoff if the UI already shows the product as active."
  - "OWNER: confirm a BUSINESS/ENTERPRISE license or written commercial grant before calling AD-1 rights-safe. Do not solve production with a personal-use plan."
  - "After entitlement 200: do not merge a code change. Let the normal scheduled nightly produce capture S, then capture D, both coverage_pct >= 0.90, health receipt healthy, no --force."
  - "Only after S+D: run AD-1 production path and Sol production-acceptance review. Then, separately, Sol may commission Massive↔ThetaData parallel-source adjudication."
do_not_redo:
  - "Polygon-vs-Massive domain migration as the cause (falsified twice: 2026-08-19 morning census and 2026-08-19T19:59:29Z coordinator reproof)."
  - "A coding-agent 'fix Polygon options' sweep, base-URL flip, retry inflation, threshold change, or AD-1 scoring edit while the chain endpoint is 403."
  - "375-symbol collector while entitlement is down."
  - "Silent AD-1 route to ThetaData or Cboe delayed-quote scrape."
  - "Manual reconstruction of 2026-08-14/17/18 chain files."
  - "Resurrecting W1A / sparse selector before AD-9."
  - "Starting AD-2, AD-6, or AD-7."
danger_areas:
  - "data/polygon_gex_health/ is nightly-written runtime state — never commit a diagnostic receipt."
  - "A write into omitted sparse-tree data/ truncates committed parquet. This recovery worktree is a full checkout; other sessions may not be."
  - "HTTP 200 on stocks is not an Options grant and is not a commercial license."
discoveries:
  - "DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION"
---

## Owner action packet

Verdict for Sol: **ENTITLEMENT_STILL_BLOCKED**.

No code PR. The chain endpoint is still 403 on both official domains. Massive's
Options Snapshot contract still requires a qualifying Options subscription.
Mastermind is a commercial product — restore under a business/enterprise grant,
not an assumed personal plan.

### Exact main

Session-start fetch: `7b436da928a7cccc504d78bb0e04ed427c71ed7b`
(hot-tape 2026-08-19T19:44Z). Coordinator 8-probe ran against
`164d7ea41f6e7a2262ac3151b5cb276b1c39871b`. Agent OS edits land on
`418c583754a6` (later origin/main). All three SHAs contain #5872 and #5974.

### Safe differential census (coordinator reproof)

Probe time: **2026-08-19T19:59:29Z**.
Key source name: **MASSIVE_API_KEY** (length 32). POLYGON_API_KEY absent from
local env. GitHub Actions secret **POLYGON_API_KEY** exists
(`updated_at` 2026-08-08T08:10:36Z). No Actions secret named MASSIVE_API_KEY.

| domain | class | HTTP | verdict | body | nonempty | request_id |
|---|---|---|---|---|---|---|
| api.polygon.io | AAPL stock snapshot | 200 | entitled | OK | true | c1b8700d10d72ed465a13a3ead2dcb77 |
| api.polygon.io | AAPL option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | fd56f7ecc3704901de3576d65367940e |
| api.polygon.io | SPY option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | 9cff3f7301be3aba1c3dda1e39117a16 |
| api.polygon.io | news | 200 | entitled | OK | true | 77eb7f3e064ad400299497120902353a |
| api.massive.com | AAPL stock snapshot | 200 | entitled | OK | true | bc1226e6afcfcafa24604d9c65e81a20 |
| api.massive.com | AAPL option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | 50ee12b44116050356665b9b526b9ef5 |
| api.massive.com | SPY option-chain snapshot | 403 | not_entitled | NOT_AUTHORIZED | false | d057e08c0960818fd6afd0ae0ef4edeb |
| api.massive.com | news | 200 | entitled | OK | true | 5398152bf120b6fd9e36d17475023384 |

Required capability: Options Snapshot + daily OI + Greeks/IV.
If the account UI already shows that product active, contact Massive support
with the four chain request_ids and the 2026-08-08 entitled receipt
(`data/massive/capability_manifest.json`, `options_chain_snapshot` HTTP 200
under POLYGON_API_KEY). Stock endpoints still answering 200 is the control.

### Agent OS reconciliation

WS:ADVANCED-DATA-OPTIONS no longer claims #5872 awaits review/CI.
AD-1 runtime = done/merged. AD-1C0 = done/merged. Workstream status = blocked
on this entitlement. AD-2 stays CLOSED. ThetaData recorded as candidate only.
