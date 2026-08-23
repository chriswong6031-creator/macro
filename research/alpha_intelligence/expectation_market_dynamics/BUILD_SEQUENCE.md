# K3E Build and Acceptance Sequence

## Dependency graph

```text
K3E-0 architecture/records freeze
  ├─ SRC-A1 raw prospective EPS/revenue accrual ─ SRC-A1P natural accrual proof
  ├─ VEND-0 vendor bake-off evidence
  └─ EVAL-0 immutable evaluation preregistration

SRC-A1P + VEND-0 + EVAL-0 adjudication
  ├─ EXP-1 deterministic expectation surface baseline
  └─ MKT-1 owner-native market response view

EXP-1 + MKT-1
  └─ CPL-1 decomposed coupling/dynamics baseline
       ├─ CASE-1 historical/adversarial casebook run
       └─ EVAL-1 prospective shadow evaluation
            └─ PROD-1 Market OS reference-only golden vertical
                 └─ PROMOTE-1 owner-gated proposal, only if evidence warrants
```

## Wave contracts

| Wave | One independently useful capability | Required stop receipt | Explicitly forbidden |
|---|---|---|---|
| K3E-0 | Durable canonical architecture, ownership and cold-reader commissions | Merged exact bytes, Agent OS validation, no runtime diff | Any source/model runtime |
| SRC-A1 | Raw prospective multi-horizon EPS/revenue observation and attempt accrual | Tests, schema, mutation/idempotency proof, exact source attempt; state no higher than `BUILT_NOT_PROVEN` without natural schedule | Phases, scores, price coupling, backfill |
| SRC-A1P | Natural scheduled accrual reliability packet | Exact host/job/attempt/observation/correction/gap receipts over declared window | Calling a manual run operational |
| VEND-0 | Same-sample, rights-aware vendor decision packet | Payload/schema/coverage/rights receipts or `SAMPLE_REQUIRED` | Contract signature, marketing-only winner |
| EVAL-0 | Immutable preregistration artifact | Content hash, protocol validation and proof it precedes advanced tuning | Model tuning/outcome selection |
| EXP-1 | Deterministic expectation surface and abstention reasons | Fixture + natural input evaluation against boring baselines | Universal baseline ownership, fair value |
| MKT-1 | Owner-native response vector with lawful clocks | Fixed-window fixtures and owner reference receipts | Rival price/residual/event store |
| CPL-1 | Decomposed temporal coupling baseline | Golden/adversarial fixtures, dual-read conflict proof | Scalar gap/grade or causal claim |
| CASE-1 | PIT-authentic casebook return | Coverage, episode-honest N, missing panel and adverse cases | Hindsight backfill |
| EVAL-1 | Prospective shadow evaluation | Locked-era metrics, denominator and red-team packet | Promotion from CI or green dashboards |
| PROD-1 | Market OS owner-accepted reference projection | Real rendered/entitled product evidence and negative controls | New publication plane or hidden authority |
| PROMOTE-1 | A proposal to existing owners | Eval OS/fusion/owner decision receipts | Self-granted rank/gate/Prophet authority |

## Dispatch law

- A worker receives one wave and returns before it is extended.
- One wave equals one useful PR; unrelated repairs and next waves are excluded.
- Current canonical source owners, open PRs, worktrees and Linear cells are
  re-pinned at every dispatch.
- Every commission lists `IN SCOPE`, `OUT OF SCOPE`, `ACCEPTANCE`, `STOP` and
  `RETURN PACKET`.
- K3E-0 accepts only records. The first three lanes start only after those
  records are on current `main`.
- EXP/MKT/CPL runtime waits for adjudication of all three first-lane returns.
- Production, deploy and authority remain separately proven states.

## Program completion

The program is not complete when code merges. Completion requires a useful,
PIT-honest vertical that traverses source → expectation surface → owner market
response → decomposed temporal dynamics → prospective evaluation → accepted
Market OS projection, plus explicit adverse/null evidence and an authority state
that remains descriptive unless separately promoted.
