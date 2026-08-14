<!-- GENERATED — DO NOT EDIT BY HAND. Regenerate with `python3 scripts/agentos.py status`. Authored truth lives in agentos/; this file is derived (invariant I3). Advisory only: it reports state and gates nothing (invariant I1). -->

# Agent OS state

Generated: 2026-08-14T03:07:03Z  |  6 workstreams (4 active · 2 blocked)

| Input | Value |
|---|---|
| active_builds | data/governance/active_builds.json@2026-08-14T03:07:03.090849+00:00 |
| active_builds age | 0.0h |
| worktrees | 1 |
| records | 6 WS · 19 DEC · 5 DSC · 1 handoffs |

## Degraded inputs

- active_builds.v1 merged window is TRUNCATED — a merged PR may read 'unknown'
- Mastermind checkout not found — p0 ids unvalidated, P0 ranking neutral
- uncommitted-work scan skipped over 1 worktrees (one `git status` each) — re-run with --scan-uncommitted for stranded work

## Workstreams

| Key | Status | Owner | Program | Waves | PRs | Next action |
|---|---|---|---|---|---|---|
| [`WS:AGENT-OS`](../agentos/workstreams/WS-AGENT-OS.md) | active | chairman | project-active-build-control | done:2 in_progress:1 todo:2 | #5472(merged) #5556(merged) #5472(merged) | Close W1's remaining gate: >=3 genuine handoffs from sessions other than the scaffolding sessions, accrued from real work as adopted instructions take effect. Then Phase 3 (compile-context), which gains the agenda-integration wave that retires the UNBLOCKED list. All five conflicts remain ruled: C1 no task store, C2 claims advisory-only, C3 readiness feeds the agenda, C4 stores stay separate, C5 CXI-R12 overruled. |
| [`WS:CN-LIMIT-ALPHA`](../agentos/workstreams/WS-CN-LIMIT-ALPHA.md) | blocked | chairman | china-system | awaiting_ci:1 done:1 todo:1 | #5438(merged) | Hold. P-A1 is armed; P-A2 is accrual-gated. |
| [`WS:GMI-THEME-GRAPH`](../agentos/workstreams/WS-GMI-THEME-GRAPH.md) | blocked | coo-fable | gmi-theme-graph | done:2 todo:1 | #5402(merged) | Wait for the 2026-08-15 scrape; then start the transmission layer. |
| [`WS:MACRO-CONTEXT-INDEX`](../agentos/workstreams/WS-MACRO-CONTEXT-INDEX.md) | active | coo-fable | macro-context-index | done:1 in_progress:1 todo:1 | — | Drive the benchmark gates green (W1). |
| [`WS:PROPHET-US-ENTRY-TIMING`](../agentos/workstreams/WS-PROPHET-US-ENTRY-TIMING.md) | active | coo-fable | prophet-us | done:1 in_progress:1 todo:1 | #5370(merged) | Verify the 22:30Z bake (W1). |
| [`WS:WATCHLIST-PORTFOLIO-CEO`](../agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md) | active | coo-fable | terminal-user-services | done:2 todo:1 | #5457(merged) #5463(merged) | Obtain the persistence-model ruling, then start W1. |

## Needs a CEO ruling

- **WS:WATCHLIST-PORTFOLIO-CEO** — Portfolio and Watchlist persistence: one table or two? (blocks 1 wave(s) · wanted by 2026-08-14) — `agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md`

## Unblocked work (readiness, not assignment)

- `WS:AGENT-OS` W3 — Phase 3 — compile-context over the existing context index
- `WS:WATCHLIST-PORTFOLIO-CEO` W1 — Persistence model implementation

## Warnings

- WS:AGENT-OS — record_disagrees_with_execution: wave W1 is 'in_progress' but PR #5556 is merged
- WS:CN-LIMIT-ALPHA — record_disagrees_with_execution: wave P-A1 is 'awaiting_ci' but PR #5438 is merged
