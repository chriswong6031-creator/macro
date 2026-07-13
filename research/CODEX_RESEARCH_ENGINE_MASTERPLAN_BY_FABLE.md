# Codex Research Engine (CRX) — ChatGPT-OAuth research lane + 7-key Claude pool

**Author:** Fable (main loop), operator-directed 2026-07-13
**Status:** BUILD (operator order — not a loop-authored proposal)
**Prior art:** Signal Foundry (SF-R*), Winner Case Library (winner_case.v1 + CODEX_WINNER_CASE_PROMPT.md), Metabolism V10 throttle, key_pool/llm_auth pool economy.

## 0. Operator intent

Use idle ChatGPT-subscription (Codex) tokens — alongside up to 7 Claude OAuth
keys — to power autonomous research: winner case studies for the long-hold
lobe and signal brainstorming for the experiments lane. Codex does the
research, audits it, and lands it (PRs / candidate filings). Buttons + loop
intervals + an auto mode that runs until ≤85% of session limits, then pauses
until the window resets and auto-resumes. Never redo previously brainstormed
or tested candidates; test and audit through the real harnesses.

## Part A — Claude OAuth pool: 3 → 7 keys

`POOL_CAPABILITY_IDS` grows to `claude_code_oauth_1..7`;
`config/capability_manifest.yml` gains entries 4..7 (operator PR — the file is
loop-immutable, not operator-immutable); every workflow env block that passes
`CLAUDE_CODE_OAUTH_TOKEN_1..3` passes `_4.._7` too (absent secrets are simply
"not present" — `discover_present_keys` is presence-based, so the operator can
add keys one at a time in GitHub secrets with zero further code changes).
`METAB_KEYS_ENABLED` accepts `1..7`. The existing balancer (cooling → lowest
5h window load) and V10 usage capture extend automatically (both iterate
POOL_CAPABILITY_IDS).

## Part B — Codex research lane

### B1. Boundary rulings (CRX-R*)

- **CRX-R1 (gates are the law).** Codex output NEVER bypasses the existing
  deterministic admission gates: winner cases must pass
  `engine.winner_autopsy.parse_case_file` + the `test_winner_autopsy` contract
  (schema `winner_case.v1`, banned-language checks); signal specs must pass
  `engine.signal_foundry.screen.screen_candidate()` (7 gates + blocklists +
  construction-hash dedup). Codex is a *generator and auditor*, not an
  admission authority. All outputs display-tier; no scored-path writes.
- **CRX-R2 (not the Research Factory).** This lane does NOT touch
  `data/research_factory/` or `engine/research_factory/` and does NOT activate
  the deferred RF_AUTO_SCHEDULING program (RF-16 deferral stands untouched).
  Signal specs flow through the Signal Foundry seams (SF-R6 weekly
  idempotency, SF-R10 write fence, SF-R12 no LLM confidence scores) and
  winner cases through the case-library seam. Factory adoption of anything
  produced here remains a separate human-gated act.
- **CRX-R3 (candidate memory).** Case lane: `data/codex_lane/case_attempts.jsonl`
  (episode key `TICKER_YYYY`, status ∈ generated|audit_failed|pr_opened|
  skipped) + the existing `research/winners/cases/*.md` inventory — an episode
  attempted or shipped is never regenerated. Signal lane: the EXISTING
  memory is authoritative — `data/signal_foundry/candidates.jsonl`
  construction-hash + name dedup vs `signal_lab.REGISTRY` + frontier docket +
  `config/signal_foundry_blocklist.yml` + compiled kill registry; the codex
  generator prompt embeds prior candidate names/hashes and blocklist themes so
  brainstorming avoids them upstream of the hard gates too.
- **CRX-R4 (budget honesty + 85% cutoff).** Every `codex exec` run parses the
  JSONL event stream for token counts and rate-limit snapshots (5h primary /
  weekly secondary `used_percent`, reset hints) into
  `data/codex_lane/usage_state.json`. The loop gate refuses new sessions when
  either window's used_percent ≥ `budget_pct` (config, default 85) OR after a
  usage-limit error, writing `paused_until` (reset hint, else now+5h primary /
  now+7d secondary fallback). Auto mode resumes when `paused_until` passes.
  When Codex reports no usage data (older CLI), the lane falls back to
  error-based backoff and a conservative per-window session cap
  (`max_sessions_per_window`, default 10) — honest degraded mode, labeled.
  Anthropic-style hard resets to 0 are handled by trusting the latest
  reported snapshot over any local estimate.
- **CRX-R5 (audit before landing).** Case lane: after generation, a
  deterministic audit (parse gate + filename/ticker/year match + required
  sections + URL-presence + banned-language) then a SECOND independent codex
  audit session running the documented batch-audit checklist (contract/tape/
  evidence passes from CASE_LIBRARY_EXPANSION_25) returning PASS or findings;
  findings → one fix cycle → re-audit; still failing → status audit_failed,
  never shipped. Signal lane: admitted specs are immediately harness-tested
  (`run_signal_foundry_harness`) — the battery verdict IS the audit; an
  optional codex skeptic note is advisory-only (SF-R12: categorical, no
  scores).
- **CRX-R6 (landing).** Case lane ships a branch + PR per case
  (`codex/case-<ticker>-<year>`), DRAFT by default (`case_pr_mode: draft` in
  config; operator may set `ready`) — merge stays with the operator/babysitter.
  The lane never merges and never pushes to main. Signal lane "lands" by
  filing candidates + harness results into the existing SF stores (its normal
  admission path).
- **CRX-R7 (kill switches + operator-only knobs).** Repo variables:
  `CODEX_MODE` (`off|interval|auto`, absent=off — fail-closed for a
  token-spending lane), `CODEX_INTERVAL_HOURS` (default 6),
  `CODEX_LANES` (`cases|signals|both`, default both). Set via admin panel or
  `gh variable set`. `config/codex_lane.yml` is operator policy (budget_pct,
  quotas, timeouts, pr mode, sandbox) — loop-immutable (self-mod fence).
- **CRX-R8 (auth + secrets hygiene).** Codex auth lives in `~/.codex/auth.json`
  on the runner box (operator installs codex CLI + `codex login` once — same
  pattern as the claude CLI install). Tokens never transit logs, ledgers, or
  GH secrets. The runner resolves the codex binary like the claude resolver
  (PATH → known install dirs).

### B2. Components

| Piece | What |
|---|---|
| `engine/codex_lane/runner.py` | codex CLI wrapper: binary resolver, `codex exec --json` subprocess with timeout, JSONL event parser (final message, token counts, rate-limit snapshots, usage-limit/auth error classification), NEVER-RAISE |
| `engine/codex_lane/budget.py` | usage_state.json read/write, `can_run()` gate (85% rule, paused_until, degraded session-cap fallback), `note_usage()/note_limit_hit()` |
| `scripts/codex_case_lane.py` | one iteration: pick next episode (uncased `winner_episodes.parquet` rows ranked by excess return, minus attempts ledger) → fill CODEX_WINNER_CASE_PROMPT.md → codex generates case → deterministic audit → codex audit session → fix cycle → branch + draft PR → ledger row |
| `scripts/codex_signal_lane.py` | one iteration: build SF context pack (reuse `_build_sf_pack`) → codex generates specs → existing screen gates admit/reject → file into `candidates.jsonl` → run harness on admitted ids → ledger/governance rows (SF write-fence respected) |
| `scripts/codex_research_loop.py` | the loop driver: reads CODEX_MODE/LANES, runs iterations of enabled lanes until budget gate refuses or per-run iteration cap; writes loop journal `data/codex_lane/loop_journal.jsonl` |
| `.github/workflows/codex-research.yml` | self-hosted; dispatch inputs (lane, iterations, force) + 2h cron; cron gate: CODEX_MODE=off→no-op; interval→run if hours since last loop ≥ CODEX_INTERVAL_HOURS; auto→always attempt (budget gate inside does the 85%/pause logic); commits `data/codex_lane/**` + SF stores narrowly |
| `config/codex_lane.yml` | budget_pct 85, max_sessions_per_window 10, session_timeout_min 25, signals_per_run 5, cases_per_run 1, case_pr_mode draft, codex_model "", sandbox "workspace-write", network true (cases need source URLs) |
| Admin panel | Codex Research card: mode selector, interval, lanes, usage bars (5h/weekly used% + resets, reported vs estimated), run-now buttons (cases / signals / both), recent attempts + PRs list; routes `/api/codex/{panel,mode,run}` |

### B3. Honest constraints (stated up front)

- Usage precision depends on the codex CLI version's event stream; the parser
  accepts multiple shapes and degrades to error-based backoff + session caps
  when absent (CRX-R4). First live runs will confirm which fields the
  installed CLI emits.
- The operator must install the codex CLI on the runner box and `codex login`
  once (auth.json exists on the dev box already; the Studio needs its own).
- Case-lane PRs are only as good as the audit; the parse gate is the hard
  floor, the codex audit is best-effort — merge authority stays human while
  `case_pr_mode: draft`.

## Waves

- **W1 (this build):** Part A + runner/budget + both lanes + loop driver +
  workflow + admin card + config + tests + ci wiring.
- **W2:** per-episode case quality scoring vs the batch-audit rubric; codex
  skeptic pass wired as an SF advisory lens; usage sparklines.
- **W3:** cross-lane scheduler (codex vs claude key pools arbitraged by
  whichever has headroom).
