# Marketing Suite — 2026-07-23 full audit, operator console, and forward roadmap (by Fable)

Operator-triggered sweep ("full sweep audit and review of Marketing… make it much more user
intuitive… upgrade very hard"). This file is the program record + the roadmap for what remains.

## §0 ACCEPTANCE GATES for every future marketing lane

Not done unless:
1. The operator can see AND act on the change from the admin console (no "edit this JSONL" steps
   in user-facing flows; manual file edits may exist only as documented fallbacks).
2. Every panel answers "so what do I do" in plain words; honest empty states say WHEN data arrives.
3. End-to-end proof in the PR body: seeded-root screenshots for UI, before/after counts for engine.
4. All touched test files verified present in the ci.yml whitelist (test-whitelist-rot check).
5. No LLM originates signals/scores; sentinel/gates only de-escalate. Ledgers append-only;
   nightly remains the sole advancer of forward ledgers (publish lane commits only its own outbox/
   receipts/metrics files).
6. Dark-by-default for anything that touches the live X account; the kill switch
   (`MARKETING_PUBLISH_ENABLED` unset) must always instantly revert every path to dry-run.

## 1. What the audit found (all root-caused with file:line evidence, 2026-07-23)

| Symptom (operator report) | Root cause | State |
|---|---|---|
| "No new posts for days; Outbox empty; Publisher empty" | Nightly WROTE fresh plans + outbox but never `git add`-ed them (staging gap; outbox flag also landed post-run). | Fixed by #3326 (07-23 13:57 PT). First real fill = the 07-23 nightly. |
| "Posts have no timestamp" | Plan items carry slot codes only (`D1-AM`); admin never surfaced `as_of`/derived times. | Fixed: engine `slot_datetime` + console freshness banner + per-post times (#3347/#3348). |
| "12 cleared but I can't see them" | Sentinel report emitted only the integer `counts.passed`, no list. | Fixed: `passed` list in report + console cards linking to Outbox (#3347/#3348). |
| "14 held but nothing to press" | No console action existed (manual JSONL edit instruction). | Fixed: Allow button → `sentinel_exceptions.jsonl` via POST (#3348). |
| "85 trimmed by caps every night" | `max_posts_per_account_per_day` applied plan-wide (7 days), not per-day. | Fixed: per-day bucketing (#3347). |
| "Accounts all live but only Flagship exists" | `status="warming"` hardcoded for all 6; no `enabled`/`handle` in config; generation ran for all 6. | Fixed: `enabled` config + operator override file + live/ready/planned derivation + enabled-only generation (#3347), console toggle (#3348). |
| "Channels shows nothing about accounts/posts" | Posted receipts only reached `outbox/status_ledger.jsonl`; `publications.jsonl` (feeds the page) had 1 seed row; handle never rendered. | Fixed: publisher→publications bridge (#3347) + account panels w/ recent posts (#3348) + metrics join (#3346). |
| "No pictures on posts" | Only ≤12 featured charts get SVGs; publisher skipped media entirely (Buffer needs public URLs). | #3346: PNG render at plan time + R2 public upload + Buffer `assets` attach (needs R2 env on the nightly runner step — wired in the same PR). |
| "Is dup-check burning tokens?" | No — pure-local token-Jaccard (`sentinel.py`), zero LLM calls, sub-ms. | Console copy now says so. |
| "Dry run: nothing approved and due" | Correct behavior over an empty outbox + dark publisher. | Console explains the why + go-live checklist (#3348). |

## 2. What shipped (2026-07-23/24)

- **#3347** engine correctness: per-day sentinel caps; `passed` list; account liveness model
  (`engine/marketing/accounts.py`, config `enabled`/`handle`, `data/marketing/account_overrides.json`);
  enabled-only generation; no-channel expiry (3d → `expired_no_channel`); publications bridge;
  `slot_datetime`; content payload timestamps.
- **#3348** operator console: pipeline rail (Plan→Gate→Outbox→Publisher→Posted) + "Needs you" rail;
  sentinel passed-cards + Allow flow; account on/off toggles (override file + allowlisted
  gitops commit/push); publisher go-live checklist (incl. token-rotation warning) + slot countdown +
  dry-run zero-breakdown; campaigns honest reframe; outbox empty-state/timestamps; nav pending-dot.
  Hardened: input length caps, known-account validation, in-function deployed refusal.
- **#3346** metrics + media: Buffer `post{metrics, externalLink}` poller →
  `data/marketing/post_metrics.jsonl` (+ workflow step & commit-back); admin publisher metrics join;
  PNG signal charts (PIL) at plan-build; R2 public upload (`marketing/charts/<as_of>/<id>.png` on the
  existing public data plane); publisher attaches `media_url` via Buffer `assets`. Follower counts are
  NOT in Buffer's API (see roadmap).

## 3. Go-live state (operator actions, in order)

1. Rotate the Buffer token (old one was exposed in a chat log), then set repo secrets
   `BUFFER_TOKEN` + `MARKETING_PUBLISH_ENABLED=1` (runbook §1/§6). Until then everything is
   shadow/dry-run BY DESIGN — the console Publisher page tracks this checklist live.
2. After the first fresh nightly: review Outbox → Approve. Publisher posts at 14:00/17:30/20:15 UTC
   weekdays (7:00/10:30/13:15 PT). Metrics appear ~24h after posting (Buffer refresh cadence).
3. Keep `auto_approve: false` during warm-up (runbook §9); the mover/theme publish-time carve-out is
   the only no-human path and is tape-verified at post time.

## 4. Roadmap (adjudicated, not yet built)

| Lane | What | Notes / routing |
|---|---|---|
| Follower history | Nightly `GET /2/users/:id?user.fields=public_metrics` (X API pay-per-use, ~$0.30/mo) → `follower_history.jsonl` + console sparkline | Needs operator to create an X developer account + billing. Builder lane once keys exist. |
| Weekly digest | Monday console card + optional email: posts, impressions, best/worst, follower delta, next experiments | Builder (opus) after 2+ weeks of metrics accrue. |
| Copy learning loop | Join `post_metrics.jsonl` × template/kind/`_copy_mode` → per-template performance in Lab; deterministic re-weighting of template banks (display-tier until gauntleted) | Engine lane; LLM may only de-escalate. |
| Second desk activation | Criteria: flagship ≥4 wks clean posting + operator creates the X account + Buffer channel; then toggle on in console | Operator decision; console toggle already supports it. |
| Campaigns activation | Wire opportunity→campaign compiler to a real funnel target (tools pages), with budget envelope + experiment cell; until then page stays honestly "seeded" | Needs its own charter; do NOT bolt on. |
| Image variety | Share-card PNGs (watchlist v2 exists) for non-signal kinds; og-image reuse | Builder, after media lane proves out live. |
| Replies/community desk | Reply queues exist in engine naming only; real build needs read-API budget decision | Defer; revisit with follower lane. |

## 5. Standing traps (learned this sweep)

- The nightly checks out at job START (~15:30 PT) but the marketing governor step runs ~20:45 PT —
  same-day merges may miss that night's run by hours. Judge "did my fix ride" by checkout time.
- `gh pr checks`: "Workers Builds: macro" red is the documented spurious check.
- Admin preview tooling caches a worktree root — drive dev runs via `MACRO_ADMIN_ROOT` env.
- Never re-fix a red lane against a stale checkout; re-run vs fresh main first (see memory).
