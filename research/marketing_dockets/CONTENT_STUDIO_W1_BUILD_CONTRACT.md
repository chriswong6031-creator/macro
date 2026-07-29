# Content Studio W1 build contract (2026-07-29)

Interface pin between Builder A (copywriter/critic/facts) and Builder B
(content_studio/outbox/publisher/config). Masterplan:
`research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md` (§0 gates
binding). Neither builder edits the other's primary files; both code to THIS
contract. Integration + seam fixes happen in the commissioning session.

## Ownership

- **Builder A**: `engine/marketing/copywriter.py` (writer v2, validate_copy_v2,
  display rounding), NEW `engine/marketing/copy_critic.py`,
  `engine/marketing/market_facts.py` (denominators + jargon-string sweep),
  NEW `scripts/marketing_copy_dryrun.py`, their tests.
- **Builder B**: `engine/marketing/content_studio.py` (selection layer, shape
  mixer, allocation, plan report counters), `engine/marketing/outbox.py`
  (shape-aware emit, no-fallback refusal, stale-queued expiry),
  `scripts/marketing_publisher.py` (kind-scoped auto-approve),
  `config/marketing.yml` (new blocks), NEW
  `.github/workflows/marketing-copy-dryrun.yml`, their tests.
- Nobody touches: `sentinel.py`, `hot_tape_llm.py`, `press_lane.py`,
  `value_gate.py`, ci pack lane lists EXCEPT adding new test files to the
  marketing-engine lane run line + ci.yml trigger paths (both builders list
  their new test files; commissioning session merges the lists).

## Shapes

`SHAPES = ("one_liner", "two_part", "stack", "list", "caption")`
- one_liner: single line, ≤140 chars, NO headline.
- two_part: headline (≤90) + blank line + body (≤275). The ONLY shape with a
  headline.
- stack: 2–5 lines separated by single `\n`, ≤275 total, no headline; numbers
  escalate or enumerate.
- list: 2–6 ticker/number rows + at most one read line, single `\n`, ≤275, no
  headline.
- caption: ≤90 chars, no headline, REQUIRES media attached at emit (chart does
  the talking).
Storage: `ContentItem.body` carries the full shaped text (may contain `\n`);
`headline` is `""` except two_part. `outbox.compose_text(headline, body)`
already drops empty parts — unchanged signature.

## Context contract (build_context output, consumed by writer/validators)

Existing fields keep meaning. New/changed keys (Builder A implements, Builder B
supplies inputs via plan_account → the copywriter pass):
- `shape`: one of SHAPES (assigned by B's mixer; A's writer/validators obey).
- `angle`: short str from
  `("level_watch","risk_frame","group_read","precedent","process",
    "receipt_frame","macro_read","event_read")` — B assigns; A folds into the
  prompt as the post's job.
- `sibling_texts`: list[str] — same-ticker posts already written tonight on
  other accounts (B threads them through sequentially per ticker); writer must
  diverge; A's validator rejects ≥6-gram overlap with any sibling.
- `numbers_whitelist`: DISPLAY-ROUNDED strings only (rounding law below).
- `pack`: optional dict for the ticker from `data/marketing/hot_tape_pack.json`
  (keys as found: streak/since-date/52w-distance material). Absent → omit.
  Read-only join, no import of radar modules; tolerate missing file (B loads
  once per plan build and passes per-ticker slices).

## Rounding law (Builder A, single formatter `format_display_price`)

- price ≥ 100 → integer ("285"); 10 ≤ p < 100 → 1 decimal, strip trailing .0
  ("34.4", "81.4", "45"); p < 10 → 2 decimals ("4.87").
- percents → 1 decimal, strip trailing .0 ("6%", "2.3%").
- Applies to entry/t1/t2/invalidation/level/reference prices in fact strings
  AND the whitelist. Full-precision values remain in item provenance and are
  NOT in the whitelist. validate_copy_v2 rejects `\d+\.\d{2}` tokens whose
  value ≥ 10 (fake-precision rule d).

## Writer API (Builder A)

```python
write_posts_llm_v2(contexts, cfg) -> list[dict]   # same order as input
# each: {"text": str, "headline": str, "body": str, "mode": "llm"|"llm_repair",
#        "critic": {"verdict": "pass", "reasons": []}}
#   or: {"mode": "dropped", "reasons": [...], "stage": "provider"|"validate"|"critic"}
```
- Per-item model call (ThreadPoolExecutor, `cfg.llm.max_workers` default 4,
  per-call max_tokens `cfg.llm.per_post_max_tokens` default 400), JSON
  `{"text": ...}` output, `llm_auth` waterfall exactly as today, usage lane
  "marketing-copywriter".
- Flow per item: write → validate_copy_v2 → (violations → ONE repair call with
  violations listed) → validate → copy_critic.cold_read_verdict → (reject →
  ONE repair → validate+critic) → pass | dropped. Never raises; one item's
  failure never affects another.
- `write_posts_llm` (v1) stays for compatibility but planned-lane callers move
  to v2. `write_posts_deterministic` unchanged (tests + wire fallbacks).
- Prompt: v1's system prompt content is the base; ADD shape contract, angle,
  sibling-divergence, cold-read law, corpus shape guidance, denominator rule,
  rounding examples; REMOVE the two-line assumption and the batch-JSON framing.
  Keep expression_dial.apply_pass on output (existing).

## Critic (Builder A, `engine/marketing/copy_critic.py`)

`cold_read_verdict(text, ctx, cfg) -> {"verdict": "pass"|"reject",
"reasons": [str]}` — separate model call, fresh context (text + kind + shape +
whitelist only, NO persona card, NO fact packet beyond a one-line topic),
usage lane "marketing-critic", max_tokens ≤200, JSON out. Checklist in prompt:
(1) parses with zero context; (2) no dangling reference; (3) no internal
jargon (screen/board/graded/plan/model/system/count-without-denominator);
(4) no orphan hedge tail; (5) sounds like a person typing, not a bot
(uniform clipped cadence, aphorism stacking = reject); (6) no advice language
on non-signal kinds. Config `copywriter.llm.critic.enabled` default true.
De-escalation only: the critic can never add facts or rewrite.
Provider failure → `{"verdict": "pass", "reasons": ["critic_unavailable"]}`
plus a `::warning` (bare print, line start) — the WRITER lane failing is fatal
for the item; the CRITIC failing is not (validators still ran).

## Selection + allocation (Builder B, content_studio)

- Cooldown: from outbox ledger (`items.jsonl` + folded status; statuses
  `queued/approved/posting/posted` count as exposure; quarantined/expired do
  NOT): ticker on any account within 3 trading days → ineligible for
  watchlist/chart/caption; 5 trading days for signal kind. Override iff a NEW
  fact class fires (earnings day, |day move| ≥4%, level break, streak-rarity
  record) — pass `cooldown_override_reason` into ctx; writer must lead with it.
- Reuse budget: (ticker, day) ≤2 accounts, disjoint angles; signal kind: 1
  account/day; count confluence + movers items toward budgets.
- Degenerate stat: numerator/denominator ≥0.95 or ≤0.05 → fact dropped, plan
  report counter `degenerate_stats_dropped`.
- Entry sanity: at plan build, signals re-checked with
  `copywriter.verify_signal_live` semantics; runaway → demote to
  watchlist_runaway kind or drop.
- Shape mixer: per (account, day): one_liner ≥25%, two_part ≤30%, ≥1 stack
  when ≥4 posts; caption only on chart-carrying items; deterministic rotation
  seeded by (account, date) — no RNG; 14-day shape ledger in
  `data/marketing/shape_ledger.json` written by the nightly only.
- Volume: emitted = min(cadence/ramp caps, surviving supply). Plan report
  gains: `supply`, `after_cooldown`, `after_budget`, `written`, `dropped`
  (by stage), `shape_mix`, `modes`.

## Emit + publisher (Builder B)

- `emit_from_content_plan`: planned kinds (`signal chart education macro
  receipt watchlist event`) REQUIRE item `mode` ∈ {"llm","llm_repair"} when
  `copywriter.llm.required` (default true). Refusals counted
  (`skipped_not_llm`) + one `::error` annotation when >0 with the lane armed;
  when the whole lane is mute (provider absent), the annotation says so (bare
  print at line start, existing mute wording extended).
- Expiry: at emit start, planned-kind items still `queued`/`approved` whose
  `scheduled_at` is >36h past → transition to `quarantined` with
  note "expired: superseded by tonight's plan" (actor `nightly_expiry`).
  (`expired` is not a ledger status; reuse quarantined + note.)
- Publisher: `publish.auto_approve_scope: "kinds"` (new, default) — auto-
  approve applies ONLY to `publish.auto_approve_kinds` (+ breaking/wire via
  their existing paths); `"all"` restores the old behavior.
  `_auto_approve_pass` honors the scope; planned kinds wait for operator
  decisions.

## Config (Builder B writes; A reads via cfg)

```yaml
copywriter:
  llm:
    enabled: true
    required: true            # planned kinds: LLM or nothing
    per_post_max_tokens: 400
    max_workers: 4
    critic: {enabled: true, max_tokens: 200}
selection:
  ticker_cooldown_days: 3
  signal_cooldown_days: 5
  max_accounts_per_ticker_day: 2
  max_signal_accounts_per_day: 1
  degenerate_stat_band: [0.05, 0.95]
shapes:
  quotas: {one_liner_min: 0.25, two_part_max: 0.30}
publish:
  auto_approve_scope: kinds   # kinds|all
```

## Tests (each builder owns their side; names are §0-gate-keyed)

- A: `tests/test_marketing_copy_v2.py` — rounding table; fake-precision rule;
  orphan-hedge rule (tail word "historical/promise/guarantee" requires a
  base-rate stat token in text); denominator rule (a bare count + "groups|
  names|stocks" without "of N" rejects); sibling 6-gram rule; shape
  conformance (headline outside two_part rejects; line counts per shape);
  per-item isolation (one poisoned context → others fine, mocked provider);
  critic mock flow (reject → repair → drop); jargon lexemes
  (screen/board/graded) reject.
- B: `tests/test_marketing_selection.py` — cooldown (LKFN yesterday →
  ineligible today; override on |move|≥4%); reuse budget (3rd account for
  ARES refused; 2nd signal account refused); degenerate stat (231/231
  dropped); shape mixer quotas + determinism; emit refusal of non-llm planned
  items under required=true (+ counter); expiry transition; auto-approve
  scope (planned kind NOT auto-approved, mover still auto-approved).
- Both files join the marketing-engine lane run line + ci.yml trigger paths
  (list them; commissioning session merges).
- Lane purity: no `anthropic`/network import at module top in ANY touched
  file (existing scan tests must stay green; providers mocked via
  `engine.llm_auth` monkeypatch).

## Dry-run (Builder A script, Builder B workflow)

`scripts/marketing_copy_dryrun.py`: loads current `data/marketing/content_plan.json`
scaffolding (or rebuilds contexts from plans if scaffolding absent), runs the
v2 writer on N items (`--limit`, default 8) WITHOUT touching the outbox,
prints per-item: old template text vs new model text, mode, critic verdict,
violations; exits 0 with a fallback-rate summary (reuses
`hot_tape_llm`-style stats counters). Workflow
`.github/workflows/marketing-copy-dryrun.yml`: workflow_dispatch, ubuntu,
minimal deps (pyyaml, requests, anthropic), repo LLM secrets (same env block
shape as daily.yml's governor step), runs the script `--limit 10`, prints to
the run log. No writes, no artifacts.

## House laws that bite here

- GH annotations: bare `print("::warning …", flush=True)` at line start, never
  through a logger.
- No em dashes in generated copy (validator); fine in code comments/docs.
- Lazy LLM imports only (marketing-engine lane has no anthropic).
- No `Date.now`-class randomness in workflows; mixer is date-seeded, no RNG.
- Ledger writes only via `outbox.transition`/`append_jsonl` canonical paths;
  nightly remains sole advancer; `shape_ledger.json` written in the nightly
  governor step only.
- The word "validated" never appears in user-facing copy.
