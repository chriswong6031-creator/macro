<!-- GENERATED — DO NOT EDIT BY HAND. Regenerate with `python3 scripts/agentos.py status`. Authored truth lives in agentos/; this file is derived (invariant I3). Advisory only: it reports state and gates nothing (invariant I1). -->

# Agent OS state

Generated: 2026-08-13T02:12:31Z  |  6 workstreams (4 active · 2 blocked)

| Input | Value |
|---|---|
| active_builds | data/governance/active_builds.json@2026-08-11T01:48:44.205959+00:00 |
| active_builds age | 48.4h |
| worktrees | 249 |
| records | 6 WS · 9 DEC · 3 DSC · 0 handoffs |

## Degraded inputs

- active_builds.v1 merged window is TRUNCATED — a merged PR may read 'unknown'
- mastermind:config/strategic_state.yml absent — p0 ids unvalidated, P0 ranking neutral (this Mastermind checkout predates config/strategic_state.yml)
- uncommitted-work scan skipped over 249 worktrees (one `git status` each) — re-run with --scan-uncommitted for stranded work
- active_builds.v1 is 48h old — PR state predates the last nightly sweep

## Workstreams

| Key | Status | Owner | Program | Waves | PRs | Next action |
|---|---|---|---|---|---|---|
| [`WS:AGENT-OS`](../agentos/workstreams/WS-AGENT-OS.md) | active | chairman | project-active-build-control | in_progress:2 todo:3 | — | Start Phase 1 (adoption). All five conflicts are ruled: C1 no task store, C2 claims advisory-only, C3 readiness feeds the agenda, C4 stores stay separate, C5 CXI-R12 overruled. Phase 3 gains the agenda-integration wave that retires the UNBLOCKED list. |
| [`WS:CN-LIMIT-ALPHA`](../agentos/workstreams/WS-CN-LIMIT-ALPHA.md) | blocked | chairman | china-system | awaiting_ci:1 done:1 todo:1 | #5438(unknown) | Hold. P-A1 is armed; P-A2 is accrual-gated. |
| [`WS:GMI-THEME-GRAPH`](../agentos/workstreams/WS-GMI-THEME-GRAPH.md) | blocked | coo-fable | gmi-theme-graph | done:2 todo:1 | #5402(unknown) | Wait for the 2026-08-15 scrape; then start the transmission layer. |
| [`WS:MACRO-CONTEXT-INDEX`](../agentos/workstreams/WS-MACRO-CONTEXT-INDEX.md) | active | coo-fable | macro-context-index | done:1 in_progress:1 todo:1 | — | Drive the benchmark gates green (W1). |
| [`WS:PROPHET-US-ENTRY-TIMING`](../agentos/workstreams/WS-PROPHET-US-ENTRY-TIMING.md) | active | coo-fable | prophet-us | done:1 in_progress:1 todo:1 | #5370(unknown) | Verify the 22:30Z bake (W1). |
| [`WS:WATCHLIST-PORTFOLIO-CEO`](../agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md) | active | coo-fable | terminal-user-services | done:2 todo:1 | #5457(unknown) #5463(unknown) | Obtain the persistence-model ruling, then start W1. |

## Needs a CEO ruling

- **WS:WATCHLIST-PORTFOLIO-CEO** — Portfolio and Watchlist persistence: one table or two? (blocks 1 wave(s) · wanted by 2026-08-14) — `agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md`

## Unblocked work (readiness, not assignment)

- `WS:WATCHLIST-PORTFOLIO-CEO` W1 — Persistence model implementation

## Warnings

- WS:CN-LIMIT-ALPHA — record_disagrees_with_execution: wave P-A1 cites PR #5438, absent from active_builds.v1 (may predate the 14d merged window — fail-open, verify by hand)
