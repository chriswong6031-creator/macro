# Metabolism V10 — Operator Throttle & Key Economy

**Author:** Fable (main loop), operator-directed 2026-07-13
**Status:** BUILD (operator order — not a loop-authored proposal)
**Prior art:** V2-B (dispatch spread + key pool), V9 (attention economy)

## 0. Operator intent (verbatim goal)

Use idle subscription tokens to power the loop: change run **intensity**,
change run **frequency**, **start runs now** at a button press (full chain,
individual stages, individual lobes, main lobe), **toggle OAuth keys** on/off
with the pool **load-balancing** across whatever is enabled, and **track
per-key 5-hour / weekly usage** in the admin panel (knowing Anthropic
sometimes hard-resets those windows to 0).

## 1. Assessment (what exists vs what's new)

Already in place: `engine/llm_auth.py` expands the OAuth pool ordered by
(cooling, ascending 5h window load) — load balancing exists; `key_pool`
ledgers per-key sessions (`est_tokens`, outcomes, cooling rows with
`reset_hint`, `window_load`, `weekly_load`); the admin panel (stdlib JSON API
+ static app.js, session+CSRF auth) already sets repo variables
(`/api/metabolism/toggle`) and dispatches workflows (`/api/deploy/dispatch`).

New in V10: the operator throttle variables, the chain-runner workflow with
pace gating, per-lobe/per-stage run buttons, the key enabled-set, and true
usage capture from Anthropic's `anthropic-ratelimit-*` response headers
(subscription OAuth exposes unified 5h/7d windows — captured opportunistically;
locally-observed rolling usage is always shown as the labeled fallback).

## 2. Operator state — three repo variables (AUTONOMY_PAUSED pattern)

| Variable | Values | Default (absent) | Effect |
|---|---|---|---|
| `METAB_INTENSITY` | `low \| normal \| high \| max` | `normal` | Scales effective docket size: multiplier 0.5 / 1.0 / 1.5 / 2.0 applied AFTER the V9 attention share, result always clamped to the IMMUTABLE `max_docket_size` (G5 preserved — intensity can only fill up to the cap, never past it; DORMANT stays 0) |
| `METAB_PACE` | `single \| 2x \| 4x` | `single` | How many chain-runner cycles per UTC day the extra crons may fire (the original daily staggered chain is untouched and always runs) |
| `METAB_KEYS_ENABLED` | csv of `1,2,3` | all present keys | Key pool enabled-set: `discover_present_keys` filters to enabled ids; empty/absent = fail-open (all). The legacy single `CLAUDE_CODE_OAUTH_TOKEN` is toggled by the id `legacy` |

Set via admin panel buttons (`github_api.set_repo_variable`) or `gh variable set`.
Read: workflows pass `${{ vars.METAB_* }}` into env; python reads env with
defaults (`engine/metabolism/throttle.py`). Loop PRs cannot set repo variables
— these are operator-only by construction.

## 3. Chain runner — `.github/workflows/metabolism-cycle.yml`

One dispatchable workflow that runs the whole chain by invoking the existing
stage workflows sequentially (`gh workflow run` + poll to completion — no
duplication of stage shell logic): agenda → propose → adjudicate → build.
(verify/audit/merge stay on their own crons — they sweep whatever exists.)

Inputs: `lobe` (empty = all loop-managed lobes; a lobe id = single-lobe
propose; `til` = the main lobe), `stages` (`full | sense | through-adjudicate`).
Cron: every 6h at :35 (offset from the daily chain), gated in-shell:
proceed only when `METAB_PACE` allows more chain-runner cycles today than have
already run (counted via `gh run list` for this workflow, UTC-day window) —
`single` → extra crons always no-op (today's behavior preserved), `2x` → 1
extra, `4x` → 3 extra. Per-cycle budget caps (IMMUTABLE) still bound each
cycle; pace deliberately multiplies daily spend — that is the operator's call.

`metabolism-propose.yml` gains a `lobe` input → `--lobe X` single-lobe path
(empty = `--all-lobes`, unchanged).

## 4. Key economy

- **Enabled-set** (`key_pool.enabled_key_ids()`): reads `METAB_KEYS_ENABLED`
  env; filters `discover_present_keys()` and the legacy token in
  `llm_auth.build_providers`. Fail-open on absent/garbage (all keys) — a bad
  toggle can never strand the loop with zero keys silently: if the filter
  yields an empty set while keys are present, log + fall back to all.
- **Balancing**: existing (cooling, window_load) ordering now runs over the
  enabled set only; `window_load` naturally spreads across however many keys
  are on.
- **Usage capture** (`key_pool.record_usage_headers` + llm_auth wiring):
  every pool client gets an httpx response event hook (via
  `anthropic.DefaultHttpxClient`) that reads any `anthropic-ratelimit-*`
  response headers and appends a compact snapshot row to
  `data/metabolism/key_usage.jsonl` (`metabolism.key_usage.v1`: ts, key_id,
  headers dict, status). Fail-soft: hook errors never affect the call.
  Header names/values are NOT secrets; token values never logged.
- **Usage snapshot** (`key_pool.usage_snapshot()`): per key —
  enabled?, cooling (+kind/reset_hint), 5h/7d observed est_tokens from the
  ledger, session counts, latest captured ratelimit headers (utilization/reset
  when Anthropic provides them), last outcome/ts. Observed windows are labeled
  ESTIMATES; header values are labeled as reported-by-Anthropic; a hard reset
  to 0 shows up as headers dropping while estimates persist — the panel shows
  both so the operator can see it.

## 5. Admin panel

- `GET /api/metabolism/throttle` — current METAB_* variable values + defaults.
- `GET /api/metabolism/keys` — `usage_snapshot()` rows.
- `POST /api/metabolism/throttle` `{intensity?|pace?|keys_enabled?, confirm}` —
  validates against the allowed vocab, `set_repo_variable`.
- `POST /api/metabolism/run` `{mode: cycle|agenda|propose|adjudicate|build,
  lobe?, stages?, confirm}` — dispatches the matching workflow
  (`metabolism-cycle.yml` for `cycle`) with inputs; workflow allowlist extended.
- Frontend (static/app.js + index.html): a "Metabolism Throttle" section —
  intensity selector, pace selector, per-key enable toggles, Run-now buttons
  (Full cycle / per-stage / per-lobe incl. Main lobe = til), and a key usage
  table (5h/7d observed + Anthropic-reported utilization + cooling/reset).

## 6. Rulings

- **R-V10-1 (operator-only knobs).** METAB_* are repo variables set by the
  operator (admin/gh). Loop-authored code never sets them. The IMMUTABLE
  budget caps remain the hard ceiling: intensity/pace scale *within* caps
  (docket clamp; per-cycle USD/token caps unchanged and still enforced).
- **R-V10-2 (fail-open defaults).** Absent/invalid variable values resolve to
  today's behavior exactly (normal intensity, single pace, all keys). A
  throttle misconfiguration can never brick the loop.
- **R-V10-3 (keys never stranded).** An enabled-set that filters to zero keys
  while keys are physically present logs and falls back to all-present.
- **R-V10-4 (honest usage).** Anthropic-reported headers are displayed as
  ground truth when present; ledger-derived rolling windows are always
  displayed and labeled estimates; the panel never fuses the two into one
  number. Hard limit resets are the operator's stated reality — reset
  timestamps from headers are surfaced verbatim.
- **R-V10-5 (chain runner reuses stages).** metabolism-cycle.yml orchestrates
  the existing stage workflows; it duplicates none of their shell logic and
  inherits every gate (AUTONOMY_PAUSED, budget, journal idempotence).
- **R-V10-6 (secrets hygiene).** Header capture logs header names/values and
  key ids only; token values never transit the usage path.

## 7. Waves

- **W1 (this build):** throttle.py + intensity hook, key enabled-set +
  header capture + usage snapshot, metabolism-cycle.yml + propose lobe input +
  env plumbing, admin routes + UI, tests, ci.yml rows.
- **W2 (deferred):** budget-aware pace (skip extra cycles when weekly reserve
  < `weekly_reserve_pct`); cortex/daily lanes honoring METAB_KEYS_ENABLED.
- **W3 (deferred):** per-key utilization sparkline; auto-pace-down on
  sustained 429 storms.
