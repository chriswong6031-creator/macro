---
key: BRIEF-LANES-PIN-THE-MANDATED-RUNG-ORDER
question: >
  The AI Daily Brief and AI Desk called DeepSeek through a hand-built ONE-RUNG
  provider list, so an exhausted DeepSeek balance blanked the brief entirely.
  Routing them onto the shared llm_auth ladder fixes that — but llm_auth's
  cooling sort can then reorder the ladder at runtime and promote the metered
  DeepSeek rung to FIRST. Accept the cooling sort as a health optimisation, or
  pin the operator's mandated order for these lanes?
answer: >
  Pin the order. Both lanes set `respect_provider_cooling: false`, so the
  configured waterfall (codex -> oauth pool -> anthropic -> deepseek) holds even
  when every subscription key is cooling. Cooling rungs are still TRIED — they
  are not skipped — they simply keep their configured position and fail fast with
  a 429 instead of yielding first place to the metered floor.
rationale: >
  The operator's instruction was explicitly about COST, not health: "priority
  being Codex oauth use, then Claude, then finally deepseek, since deepseek is
  our only pay per use provider." The cooling sort optimises for "a key another
  process just rate-limited is a bad first ask", which is correct in general and
  wrong here: it treats the metered floor as just another rung. The DeepSeek rung
  carries a cap_id and ANTHROPIC_API_KEY is not a configured repo secret, so on a
  night when every Claude key is cooling — the exact shape .github/workflows/daily.yml
  records for 2026-08-03, "all six keys 429'd" — DeepSeek is the only non-cooling
  rung and sorts to position 1. The whole night's briefs then bill to the one
  provider the change exists to stop billing, and the only trace is a log line.
  llm_auth already documents this failure class as the "SILENT ROUTING
  INVERSION"; the marketing lanes hit it in production on 2026-08-08. A failed
  429 costs a fast round-trip; a paid brief costs money and defeats the mandate.
alternatives:
  - option: Leave cooling on and rely on the existing inversion warning.
    why_not: >
      The warning is observability, not enforcement — it fires AFTER the order
      has already been inverted, into a runner log nobody reads nightly. The same
      warning existed when marketing lanes ran a whole night on DeepSeek while
      config said codex-first.
  - option: Give the DeepSeek rung no cap_id so the sort cannot move it.
    why_not: >
      cap_id is what the ai_costs ledger and key_pool cooling both key on;
      removing it to win an ordering argument would blind DeepSeek spend
      attribution, which is the other half of what this change is for.
  - option: Set a weekly OAuth ceiling on the two lanes instead.
    why_not: >
      Orthogonal — a ceiling caps how much of the Claude pool these lanes may
      consume, but does nothing about cooling promoting DeepSeek to first. Worth
      doing separately; it is not a substitute. Left open deliberately rather than
      inventing a budget number without the operator.
evidence: >
  Measured against the real build_providers with the real _ladder_cfg output and
  key_pool.is_cooling patched True for every subscription cap_id: order
  ['codex','oauth','oauth','deepseek'] became ['deepseek','codex','oauth','oauth'],
  with llm_auth's own warning "cooling demoted the configured first rung 'codex'
  below 'deepseek' for lane 'master-brain'". After `respect_provider_cooling:
  false`, the same all-cooling probe yields ['codex','oauth','deepseek'] — the
  metered rung stays last. The originating outage: with the DeepSeek key removed,
  both lanes now build 2 working rungs (codex/codex_account, oauth/claude_code_oauth_3)
  where before they had zero.
reversibility: easy
affects:
  - config.yml
  - engine/master_brain.py
  - config/capability_manifest.yml
  - .github/workflows/daily.yml
confidence: high
scope:
  - macro
  - engine/master_brain.py
  - engine/ai_desk.py
decided_at: 2026-08-27
decided_by: claude/aibrief-provider-ladder
---

## Routing a lane onto the ladder is never one edit

Three registrations must land together, and **none of them fails loudly** when
omitted — each one silently degrades the lane back toward where it started:

1. **`config.yml` `provider_order`** — the stated order.
2. **`config/capability_manifest.yml` `allowed_lanes`** — on all eight
   `claude_code_oauth*` entries, because `_oauth_pool_candidates` brokers every
   present key individually. The broker is **fail-closed**, and when a pool-aware
   lane resolves zero keys `build_providers` falls through to the single
   *deprecated* legacy token. Naming an unregistered lane is therefore strictly
   worse than naming none at all. Measured: registered → 5 rungs including
   `claude_code_oauth_3`/`_4`; unregistered → 4 rungs on the legacy slot.
3. **The workflow step's `env:`** — the runner sees only what the step passes.
   Both brief steps passed `DEEPSEEK_API_KEY` and nothing else, so every Claude
   rung was invisible at runtime no matter what the config said.

A fourth, easy to miss because it is not a routing file at all: `lib/ai_costs.py`
`_LANE_LOBE_EXACT`. A new `usage_lane` with no entry there maps to lobe
`"Other"`, quietly moving that lane's spend off its real row on the AI Cost page.

**Codex is not broker-gated.** `build_providers` calls
`codex_provider.available_accounts()` directly and never consults `resolve()`, and
Codex needs no secret in CI because it reads the runner's `~/.codex/auth.json`.
So a half-registered lane can look healthy — Codex serves, briefs appear — while
every Claude rung is silently absent. Verify with the broker itself
(`resolve(cap_id, lane=...)['allowed']`) and by diffing the built ladder against a
deliberately bogus lane name; never by reading the YAML.

## The provenance field is load-bearing, not decoration

`served_by` exists because a ladder you cannot audit is a ladder you cannot trust:
before it, every brief recorded `deepseek-v4-pro` regardless of which rung served,
so "is the balancer working?" had no answer in the artifact. Two traps found while
building it, both of which made the field lie in exactly the cases it is consulted:

- Resolve the serving model on **distinct model ids**, not provider entries. One
  provider `name` covers many rungs (one per pool token, one per Codex account)
  all sharing one model id, so an entry count of `> 1` read as "ambiguous" and left
  the label at its stale default — on precisely the pool-served runs the ladder
  exists to enable.
- The style-lint **rewrite is a second trip down the ladder** and can be served by
  a different rung than the draft. When the rewrite is accepted it becomes the
  published text, so `served_by`/`model` must follow it; otherwise the record
  describes a reply that was thrown away.

See also [[DSC-EMPTY-REPLY-DOES-NOT-WALK-THE-WATERFALL]] for the related failure
mode: `make_call` advances only on an exception, so a rung returning a 200 with no
text is treated as having served and the remaining rungs are never tried.
